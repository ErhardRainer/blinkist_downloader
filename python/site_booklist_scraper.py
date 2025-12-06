"""
Scrape Blinkist site to build a CSV of book links.

This script parses a local copy of Blinkist's sitemap.html to extract book titles and links.

Output (in this folder):
- `site_booklist.csv`: One row per book with 'Buch' (title) and 'Link' columns.
"""

import re
import html
import pandas as pd
from bs4 import BeautifulSoup

# Pfad zur lokalen sitemap.html
file_path = 'Analyse/sitemap.html'

# HTML-Datei öffnen und als Text lesen
with open(file_path, 'r', encoding='utf-8') as file:
    raw_html = file.read()

# 1) Robust regex extraction (handles malformed/embedded href values)
robust_pattern = re.compile(
    r'<li[^>]*class="[^"]*sitemap-links__item[^"]*"[^>]*>.*?<a[^>]*class="[^"]*sitemap-links__link[^"]*"[^>]*href="(?:(?:[^"]*?href=\")?(?P<link>https?://www\.blinkist\.com/de/books/[^"<>]+)[^"]*")[^>]*>(?P<title>[^<]+)</a>.*?</li>',
    re.I | re.S,
)

books = []
links = []

# Try robust regex first
for m in robust_pattern.finditer(raw_html):
    found_link = m.group('link').strip()
    found_title = html.unescape(m.group('title').strip())
    # clean possible embedded HTML inside title
    found_title = BeautifulSoup(found_title, 'html.parser').get_text(separator=' ', strip=True)
    links.append(found_link)
    books.append(found_title)

# 2) If robust regex didn't find entries, or to supplement, fallback to block parsing
if not links:
    li_pattern = re.compile(r'<li[^>]*class="[^"]*sitemap-links__item[^"]*"[^>]*>(.*?)</li>', re.S | re.I)

    for block in li_pattern.findall(raw_html):
        # Parste den Block separately with BeautifulSoup to safely handle nested tags
        block_soup = BeautifulSoup(block, 'html.parser')
        found_link = None
        found_title = None

        # 1) Try to find a direct anchor whose href contains '/de/books/' and whose text looks like a title
        for a in block_soup.find_all('a'):
            href_raw = (a.get('href') or '').strip()
            # try to extract a real /de/books/ URL even if the href contains embedded HTML
            m_inner = re.search(r'https?://www\.blinkist\.com/de/books/[\w\-\.%@\?=/&+#]*', href_raw)
            if m_inner:
                found_link = m_inner.group(0)
            else:
                href = href_raw
                if href.startswith('http') and '/de/books/' in href:
                    found_link = href

            text = a.get_text(separator=' ', strip=True)
            if text and not text.startswith('http'):
                found_title = text

            if found_link and found_title:
                break

        # 2) If no link found via parsed anchors, fallback to regex inside the raw block
        if not found_link:
            m = re.search(r'https?://www\.blinkist\.com/de/books/[\w\-\.\%@\?=/&+#]*', block)
            if m:
                found_link = m.group(0)

        # 3) If title still missing, try to build it from visible text in the block
        if not found_title:
            visible = block_soup.get_text(separator=' ', strip=True)
            # remove the link text if present
            if found_link:
                visible = visible.replace(found_link, '')
            # choose the first non-empty piece that doesn't look like a URL
            candidates = [p.strip() for p in re.split(r'\s{2,}|\s-\s', visible) if p.strip()]
            for p in candidates:
                # prefer a candidate that contains letters (not just a URL or numbers)
                if not p.startswith('http') and re.search(r'[A-Za-zÀ-ÖØ-öø-ÿÄäÖöÜüß]', p):
                    found_title = p
                    break
            # last-resort: pick the first non-empty candidate
            if not found_title and candidates:
                for p in candidates:
                    if not p.startswith('http'):
                        found_title = p
                        break

        # Final cleanup and append if both present
        if found_link and found_title:
            found_title = html.unescape(found_title)
            # clean possible embedded HTML fragments
            found_title = BeautifulSoup(found_title, 'html.parser').get_text(separator=' ', strip=True)
            books.append(found_title)
            links.append(found_link)

# Supplement with direct anchors to catch missing ones
soup = BeautifulSoup(raw_html, 'html.parser')
for a in soup.find_all('a', href=True):
    href = (a.get('href') or '').strip()
    # if href contains embedded html-like content, try to extract a clean link
    mhref = re.search(r'https?://www\.blinkist\.com/de/books/[\w\-\.%@\?=/&+#]*', href)
    clean_href = mhref.group(0) if mhref else href
    txt = a.get_text(strip=True)
    if clean_href and '/de/books/' in clean_href:
        links.append(clean_href)
        # pick a sensible title candidate
        if txt and not txt.startswith('http'):
            books.append(txt)
        else:
            # sometimes the title appears right after the anchor in the raw HTML, try to get surrounding text
            parent_text = a.parent.get_text(separator=' ', strip=True) if a.parent else txt
            candidate = parent_text.replace(clean_href, '').strip()
            books.append(candidate if candidate else clean_href)
# Deduplicate and pick best title per link (prefer non-URL titles)
final = {}
for link, title in zip(links, books):
    if link in final:
        # if we already have a title but it's just a URL, replace if new title is better
        cur = final[link]
        if (not cur or cur.startswith('http')) and title and not title.startswith('http'):
            final[link] = title
    else:
        final[link] = title

# Fallback: for links without a good title, derive one from slug
def slug_to_title(slug_text):
    s = re.sub(r'-(de|en|es|fr)$', '', slug_text, flags=re.I)
    s = s.replace('-', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return html.unescape(s)

clean_links = []
clean_books = []
for link, title in final.items():
    t = title.strip() if title else ''
    # clean any embedded HTML first
    t = BeautifulSoup(t, 'html.parser').get_text(separator=' ', strip=True)
    # if title contains a URL or is empty, fallback to slug
    if not t or re.search(r'https?://', t) or len(t) < 2:
        slug = link.rstrip('/').rsplit('/', 1)[-1]
        t = slug_to_title(slug)
    clean_books.append(t)
    clean_links.append(link)

# DataFrame erstellen und speichern
df = pd.DataFrame({'Buch': clean_books, 'Link': clean_links})
print(df.head(20))
df.to_csv('Analyse/site_booklist.csv', index=False)
