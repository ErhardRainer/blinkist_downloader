"""Compare Blinkist site list with local audio library.

This script will:
- optionally run the site-list scraper script to produce `site_booklist.csv`
- run the local library scanner script to scan a Blinkist dump folder and produce `local_blinkist_files.csv`
- load both CSVs into pandas and try to match book links (by slug) to files found
- write a comparison CSV `blinkist_existing_books_comparison.csv` and an HTML list `blinkist_missing_books.html`.
"""

from pathlib import Path
import subprocess
import sys
import pandas as pd
import re
import json
import os
from typing import Optional
from html import escape
import webbrowser
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


def run_python_script(script_path: Path, args: list[str]) -> int:
    cmd = [sys.executable, str(script_path)] + args
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    return res.returncode


def ensure_file(path: Path, desc: str, fail: bool = True) -> bool:
    if path.exists():
        return True
    msg = f"Expected {desc} at {path} but not found."
    if fail:
        raise FileNotFoundError(msg)
    else:
        print(msg)
        return False


def extract_slug_from_link(link: str) -> Optional[str]:
    if not isinstance(link, str) or not link:
        return None
    # match /de/books/<slug> (slug may contain - and url chars)
    m = re.search(r"/de/books/([^/?#]+)", link)
    if m:
        slug = m.group(1)
        # strip trailing language suffixes or params
        slug = slug.split('?')[0].split('#')[0].rstrip('/')
        return slug
    # fallback: last path segment
    try:
        slug = link.rstrip('/').rsplit('/', 1)[-1]
        return slug
    except Exception:
        return None


def compare_booklinks_and_files(booklinks_csv: Path, files_csv: Path, out_csv: Path) -> pd.DataFrame:
    df_books = pd.read_csv(booklinks_csv)
    df_files = pd.read_csv(files_csv)

    # normalize columns
    if 'Link' not in df_books.columns and 'link' in df_books.columns:
        df_books = df_books.rename(columns={'link': 'Link'})
    if 'Buch' not in df_books.columns and 'book' in df_books.columns:
        df_books = df_books.rename(columns={'book': 'Buch'})

    # Prepare file title normalization: derive a clean title part from filename (remove extension,
    # take the trailing part after the last ' - ' if present)
    def normalize_text(s: str) -> str:
        if not isinstance(s, str):
            return ''
        s = s.replace('-', ' ')
        s = s.lower()
        s = re.sub(r"[^a-z0-9äöüßàáâãçèéêíîóôúüñßèë\s]", ' ', s)
        s = re.sub(r"\s+", ' ', s).strip()
        return s

    # Prefer rapidfuzz's normalized similarity for fast, robust scoring
    try:
        from rapidfuzz.distance import Levenshtein as RFLevenshtein  # type: ignore

        def similarity_score(a: str, b: str) -> float:
            if not a and not b:
                return 1.0
            try:
                # normalized_similarity returns float in [0.0, 1.0]
                return float(RFLevenshtein.normalized_similarity(a, b))
            except Exception:
                return 0.0

    except Exception:
        # Fallback: simple normalized-distance based score using DP levenshtein
        def _levenshtein(a: str, b: str) -> int:
            if a == b:
                return 0
            if len(a) == 0:
                return len(b)
            if len(b) == 0:
                return len(a)
            previous = list(range(len(b) + 1))
            for i, ca in enumerate(a, start=1):
                current = [i]
                for j, cb in enumerate(b, start=1):
                    insertions = previous[j] + 1
                    deletions = current[j-1] + 1
                    substitutions = previous[j-1] + (0 if ca == cb else 1)
                    current.append(min(insertions, deletions, substitutions))
                previous = current
            return previous[-1]

        def similarity_score(a: str, b: str) -> float:
            if not a and not b:
                return 1.0
            dist = _levenshtein(a, b)
            maxlen = max(len(a), len(b))
            if maxlen == 0:
                return 1.0
            return 1.0 - (dist / maxlen)

    # pick file name column
    if 'absolute_path' in df_files.columns:
        file_names = df_files['absolute_path'].astype(str).apply(lambda p: Path(p).name)
    elif 'relative_path' in df_files.columns:
        file_names = df_files['relative_path'].astype(str).apply(lambda p: Path(p).name)
    else:
        # fallback to first column
        file_names = df_files.iloc[:, 0].astype(str).apply(lambda p: Path(p).name)

    file_stems = file_names.str.rsplit('.', n=1).str[0]
    # take part after last ' - '
    file_title_parts = file_stems.str.split(' - ').str[-1]
    file_title_norm = file_title_parts.apply(normalize_text)

    # track which file indices have been matched
    matched_file_idxs = set()

    results = []

    # Precompute book target normalized title from slug (preferred) or from displayed title
    book_targets = []
    for idx, row in df_books.iterrows():
        link = row.get('Link') if 'Link' in row else row.get('link')
        title = row.get('Buch') if 'Buch' in row else row.get('Buch')
        slug = extract_slug_from_link(str(link)) if link else None
        if slug:
            # derive readable title from slug
            t = slug
            # remove trailing language suffixes like -de
            t = re.sub(r'-(de|en|es|fr)$', '', t, flags=re.I)
            t = t.replace('-', ' ')
            target_norm = normalize_text(t)
        else:
            target_norm = normalize_text(str(title))
        book_targets.append((link, title, slug, target_norm))

    # For each book entry, attempt exact/substr match first, then fuzzy
    for link, title, slug, target_norm in book_targets:
        matched_idxs = []
        # exact or substring match on normalized titles
        if target_norm:
            mask = file_title_norm.str.contains(re.escape(target_norm), case=False, na=False)
            matched_idxs = [i for i, m in enumerate(mask) if m]

        # Additional slug-based match: check if slug (with hyphens) appears in the file stem
        if not matched_idxs and slug:
            slug_h = slug.lower()
            slug_h = re.sub(r'-(de|en|es|fr)$', '', slug_h, flags=re.I)
            slug_h = slug_h.strip()
            # file_stems with spaces replaced by hyphens
            file_stems_hy = file_stems.str.lower().str.replace(' ', '-', regex=False)
            mask2 = file_stems_hy.str.contains(re.escape(slug_h), na=False)
            matched_idxs = [i for i, m in enumerate(mask2) if m]
            if matched_idxs:
                match_type = 'slug'

        match_type = None
        similarity = None
        if matched_idxs:
            # mark matched files
            for i in matched_idxs:
                matched_file_idxs.add(i)
            match_type = 'exact'
        else:
            # fuzzy match: find best remaining file
            best_i = None
            best_score = 0.0
            for i, ft in enumerate(file_title_norm.tolist()):
                if i in matched_file_idxs:
                    continue
                if not ft or not target_norm:
                    continue
                score = similarity_score(target_norm, ft)
                if score > best_score:
                    best_score = score
                    best_i = i
            # threshold for accepting fuzzy match
            if best_i is not None and best_score >= 0.70:
                matched_idxs = [best_i]
                matched_file_idxs.add(best_i)
                match_type = 'fuzzy'
                similarity = round(best_score, 3)

        matched_paths = [str(df_files.iloc[i]['relative_path']) if 'relative_path' in df_files.columns else str(df_files.iloc[i,0]) for i in matched_idxs]
        status = 'found' if matched_idxs else 'missing'

        results.append({
            'Link': link,
            'Title': title,
            'slug': slug,
            'matches_count': len(matched_idxs),
            'matched_paths': json.dumps(matched_paths, ensure_ascii=False),
            'status': status,
            'match_type': match_type,
            'best_similarity': similarity,
        })

    df_res = pd.DataFrame(results)

    # Files that remain unmatched -> produce candidate matches against book list
    all_file_idxs = set(range(len(df_files)))
    unmatched_idxs = sorted(list(all_file_idxs - matched_file_idxs))
    unmatched_rows = []
    if unmatched_idxs:
        book_names = [t for (_link, _title, _slug, t) in book_targets]
        for i in unmatched_idxs:
            fname = file_title_norm.iloc[i]
            best_j = None
            best_score = 0.0
            for j, bname in enumerate(book_names):
                if not fname or not bname:
                    continue
                score = similarity_score(fname, bname)
                if score > best_score:
                    best_score = score
                    best_j = j
            unmatched_rows.append({
                'file_index': i,
                'file_name': file_names.iloc[i],
                'file_title_part': file_title_parts.iloc[i],
                'best_book_index': best_j,
                'best_book_title_norm': book_names[best_j] if best_j is not None else None,
                'best_score': round(best_score, 3) if best_j is not None else None,
            })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df_res.to_csv(out_csv, index=False)
    print(f"Wrote comparison to {out_csv} ({len(df_res)} rows)")

    # Write list of books that are missing files (only links) as a JSON file and a static HTML file.
    missing = df_res.loc[df_res['status'] == 'missing', ['Link']]
    if not missing.empty:
        # Load best list if exists
        best_list_path = out_csv.parent / 'best_list.json'
        best_set = set()
        if best_list_path.exists():
            try:
                best_list_data = json.loads(best_list_path.read_text(encoding='utf-8'))
                # Normalize best list entries to match label generation (lowercase)
                best_set = {s.lower().strip() for s in best_list_data if isinstance(s, str)}
                print(f"Loaded {len(best_set)} entries from best_list.json")
            except Exception as e:
                print(f"Error loading best_list.json: {e}")

        def transform_to_reader_url(link: str) -> str:
            try:
                p = urlparse(link)
                m = re.match(r'^/([a-z]{2})/books/(.+)$', p.path, flags=re.I)
                if m:
                    lang = m.group(1)
                    rest = m.group(2)
                    new_path = f"/{lang}/reader/books/{rest}"
                    q = dict(parse_qsl(p.query, keep_blank_values=True))
                    q['play'] = '1'
                    new_query = urlencode(q, doseq=True)
                    new_p = p._replace(path=new_path, query=new_query)
                    return urlunparse(new_p)
                return link
            except Exception:
                return link

        books_data = []
        for link in missing['Link'].astype(str):
            if not link:
                continue
            # try to extract a slug-like last segment
            slug = extract_slug_from_link(link)
            if not slug:
                slug = link.rstrip('/').rsplit('/', 1)[-1]
            # remove trailing language suffixes like -de, -en, etc.
            slug = re.sub(r'-(de|en|es|fr)$', '', slug, flags=re.I)
            # replace hyphens with spaces for a readable label
            label = slug.replace('-', ' ').strip()
            if not label:
                label = link
            
            reader_url = transform_to_reader_url(link)
            is_best = label.lower() in best_set

            books_data.append({
                'label': label,
                'url': reader_url,
                'original_link': link,
                'is_best': is_best
            })

        # Write JSON
        json_str = json.dumps(books_data, indent=2, ensure_ascii=False)
        json_path = out_csv.parent / 'blinkist_missing_books.json'
        json_path.write_text(json_str, encoding='utf-8')
        print(f"Wrote {len(books_data)} missing books to {json_path}")

        # Write Static HTML
        # We embed the JSON directly to avoid CORS issues with file:// protocol
        html_template = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Missing Blinkist Books</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; max-width: 800px; margin: 0 auto; background-color: #f9f9f9; }
        h1 { color: #333; }
        #search-container { position: sticky; top: 0; background-color: #f9f9f9; padding: 10px 0; border-bottom: 1px solid #ddd; z-index: 100; }
        .search-wrapper { display: flex; gap: 10px; align-items: center; }
        #search { width: 100%; padding: 12px; font-size: 16px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; flex-grow: 1; }
        #fav-filter { font-size: 24px; background: none; border: none; cursor: pointer; color: #ccc; padding: 0 10px; transition: color 0.2s; }
        #fav-filter.active { color: #f39c12; }
        ul { list-style-type: none; padding: 0; }
        li { background: white; margin-bottom: 8px; padding: 10px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: background-color 0.2s; }
        li:hover { background-color: #f0f8ff; }
        a { text-decoration: none; color: #007bff; font-size: 18px; display: block; width: 100%; height: 100%; }
        a:hover { text-decoration: underline; }
        a.clicked { color: #6c757d; text-decoration: line-through; opacity: 0.7; }
        a.best-book { font-weight: bold; }
        a.best-book::after { content: ' ★'; color: #f39c12; font-weight: normal; }
        .count { font-size: 0.9em; color: #666; margin-top: 5px; }
    </style>
</head>
<body>
    <h1>Missing Blinkist Books</h1>
    <div id="search-container">
        <div class="search-wrapper">
            <input type="text" id="search" placeholder="Suchen..." onkeyup="filterBooks()">
            <button id="fav-filter" onclick="toggleFavFilter()" title="Nur Favoriten anzeigen">★</button>
        </div>
        <div class="count" id="count"></div>
    </div>
    <ul id="book-list"></ul>

    <script>
        // Data embedded directly by Python script
        const booksData = __BOOKS_JSON__;
        let books = booksData;
        let showOnlyBest = false;

        function loadBooks() {
            // Sort alphabetically by label
            books.sort((a, b) => a.label.localeCompare(b.label));
            renderBooks(books);
        }

        function renderBooks(bookList) {
            const list = document.getElementById('book-list');
            const countDiv = document.getElementById('count');
            list.innerHTML = '';
            countDiv.textContent = `${bookList.length} Bücher gefunden`;

            bookList.forEach(book => {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.href = book.url;
                a.textContent = book.label;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                
                if (book.is_best) {
                    a.classList.add('best-book');
                }
                
                // Check if already clicked in this session (optional, but good for UX if list re-renders)
                // For now, we just handle the click event to add the class.
                
                a.onclick = function(e) {
                    this.classList.add('clicked');
                    // Attempt to open in background tab (best effort, browsers may block this)
                    // Standard behavior for "open in background" is usually Ctrl+Click or Middle Click.
                    // We try to simulate it by opening and refocusing parent, but modern browsers often prevent this.
                    e.preventDefault();
                    const w = window.open(this.href, '_blank');
                    if (w) {
                        try {
                            // Try to bring focus back to the list
                            window.focus();
                        } catch (ignore) {}
                    }
                };
                
                li.appendChild(a);
                list.appendChild(li);
            });
        }

        function toggleFavFilter() {
            showOnlyBest = !showOnlyBest;
            const btn = document.getElementById('fav-filter');
            if (showOnlyBest) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
            filterBooks();
        }

        function filterBooks() {
            const query = document.getElementById('search').value.toLowerCase();
            const filtered = books.filter(book => {
                const matchesQuery = book.label.toLowerCase().includes(query);
                const matchesBest = showOnlyBest ? book.is_best : true;
                return matchesQuery && matchesBest;
            });
            renderBooks(filtered);
        }

        loadBooks();
    </script>
</body>
</html>"""
        
        html_content = html_template.replace('__BOOKS_JSON__', json.dumps(books_data, ensure_ascii=False))

        miss_path = out_csv.parent / 'blinkist_missing_books.html'
        miss_path.write_text(html_content, encoding='utf-8')
        print(f"Wrote HTML report to {miss_path}")

        # Open the generated HTML in the default browser (new tab)
        try:
            webbrowser.open_new_tab(miss_path.as_uri())
        except Exception:
            try:
                webbrowser.open(miss_path.as_uri())
            except Exception:
                print(f"Could not open {miss_path} in the default browser automatically.")

    if unmatched_rows:
        un_df = pd.DataFrame(unmatched_rows)
        un_path = out_csv.parent / 'unmatched_files_candidates.csv'
        un_df.to_csv(un_path, index=False)
        print(f"Wrote {len(unmatched_rows)} unmatched file candidates to {un_path}")

    return df_res


def main():
    """Run with no CLI parameters. Uses repository-relative defaults.

    Behavior:
    - If `Analyse/book_links.csv` does not exist, runs `Booklist_scapper.py` to create it.
    - Runs `read_blinkist_files.py` against the hard-coded Blinkist directory and writes `Analyse/blinkist_files.csv`.
    - Compares both CSVs and writes `Analyse/existing_books_comparison.csv`.
    """
    # Hard-coded defaults (no CLI parameters)
    analysedir = Path(__file__).resolve().parent
    default_blinkist_dir = r'T:\_Hoerbuecher\_Blinkist\Blinkist August 2023 SiteRip Collection (GERMAN) - BASiQ'
    booklinks_path = analysedir / 'site_booklist.csv'
    files_csv_path = analysedir / 'local_blinkist_files.csv'
    comparison_output = analysedir / 'blinkist_existing_books_comparison.csv'
    include_content = False
    max_content_bytes = 1_000_000

    # 1) Ensure book links exist; if missing, run the site-list scraper
    if not booklinks_path.exists():
        sl_script = analysedir / 'site_booklist_scraper.py'
        if not sl_script.exists():
            raise FileNotFoundError(f"Could not find site-list scraper script at {sl_script}")
        rc = run_python_script(sl_script, [])
        if rc != 0:
            raise RuntimeError(f"Site-list scraper failed with return code {rc}")
        ensure_file(booklinks_path, 'book links CSV')
    else:
        print(f"Found existing book links CSV at {booklinks_path}")

    # 2) Run read_blinkist_files.py to scan the Blinkist directory
    reader_script = analysedir / 'scan_blinkist_library.py'
    if not reader_script.exists():
        raise FileNotFoundError(f"Could not find reader script at {reader_script}")

    reader_args = ['--input', default_blinkist_dir, '--output', str(files_csv_path)]
    if include_content:
        reader_args.append('--include-content')
        reader_args.extend(['--max-content-bytes', str(max_content_bytes)])

    rc = run_python_script(reader_script, reader_args)
    if rc != 0:
        raise RuntimeError(f"read_blinkist_files.py failed with return code {rc}")
    ensure_file(files_csv_path, 'files CSV')

    # 3) Load both CSVs and compare
    compare_booklinks_and_files(booklinks_path, files_csv_path, comparison_output)


if __name__ == '__main__':
    main()
