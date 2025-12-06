# Analyse Scripts

This folder contains scripts to analyze and compare Blinkist's online book list with a local Blinkist audio library dump.

## Scripts Overview

### `site_booklist_scraper.py`
Scrapes a local copy of Blinkist's sitemap.html to extract book titles and links.

**Parameters:**
- None (hardcoded to read `Analyse/sitemap.html`)

**Outputs:**
- `site_booklist.csv`: CSV with columns 'Buch' (title) and 'Link' (URL).

**Usage:**
```bash
python Analyse/site_booklist_scraper.py
```

### `scan_blinkist_library.py`
Scans a directory (e.g., a Blinkist dump folder) for files and saves metadata to CSV.

**Parameters:**
- `--input <path>`: Directory to scan (required).
- `--output <file>`: Output CSV file (required).
- `--include-content`: Include text content in CSV (optional, increases size).
- `--max-content-bytes <int>`: Max bytes to read for content (default 1MB, optional).

**Outputs:**
- `local_blinkist_files.csv`: CSV with file metadata (paths, sizes, etc.).

**Usage:**
```bash
python Analyse/scan_blinkist_library.py \
  --input "T:\_Hoerbuecher\_Blinkist\Blinkist August 2023 SiteRip Collection (GERMAN) - BASiQ" \
  --output local_blinkist_files.csv \
  --include-content --max-content-bytes 1000000
```

### `compare_blinkist_site_and_library.py`
Compares the site book list with the local library files, matches by slug, and generates reports.

**Parameters:**
- None (uses hardcoded defaults).

**Outputs:**
- `blinkist_existing_books_comparison.csv`: Detailed comparison CSV.
- `blinkist_missing_books.html`: HTML list of missing books (opens in browser).

**Usage:**
```bash
python Analyse/compare_blinkist_site_and_library.py
```

## Workflow

```mermaid
flowchart TD
    A[Start] --> B[Run site_booklist_scraper.py]
    B --> C[Generates site_booklist.csv]
    A --> D[Run scan_blinkist_library.py]
    D --> E[Generates local_blinkist_files.csv]
    C --> F[Run compare_blinkist_site_and_library.py]
    E --> F
    F --> G[Generates blinkist_existing_books_comparison.csv]
    F --> H[Generates blinkist_missing_books.html and opens in browser]
```</content>
<parameter name="filePath">w:\blinkist-scraper\Analyse\README.md