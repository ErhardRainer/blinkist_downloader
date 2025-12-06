r"""
Scan a Blinkist dump folder and write a CSV of audio(-related) files.

Small utility to read all files under a directory into a pandas DataFrame
and save it as CSV. Designed for Windows paths like

T:\_Hoerbuecher\_Blinkist\Blinkist August 2023 SiteRip Collection (GERMAN) - BASiQ\

Features:
- recursively scan directory
- collect metadata: relative path, absolute path, name, ext, size, mtime
- optionally attempt to read text content (with a size limit and fallback encodings)
- save DataFrame to CSV

Output (in this folder):
- `local_blinkist_files.csv`: One row per discovered Blinkist audio file, including path columns.

Usage example:
python Analyse/scan_blinkist_library.py \
  --input "T:\\_Hoerbuecher\\_Blinkist\\Blinkist August 2023 SiteRip Collection (GERMAN) - BASiQ" \
  --output local_blinkist_files.csv \
  --include-content --max-content-bytes 1000000
"""

from pathlib import Path
import argparse
import pandas as pd
import datetime
import os
import sys


def is_text_file(path: Path) -> bool:
    # quick heuristic: check for NUL bytes in first 4k
    try:
        with path.open("rb") as f:
            chunk = f.read(4096)
            if b"\x00" in chunk:
                return False
    except Exception:
        return False
    return True


def read_text_content(path: Path, max_bytes: int = 1_000_000):
    """Try to read file as text. Return tuple (content_or_None, encoding_or_reason)."""
    try:
        size = path.stat().st_size
    except Exception as e:
        return None, f"stat_error:{e}"

    if size > max_bytes:
        return None, "too_large"

    try:
        data = path.read_bytes()
    except Exception as e:
        return None, f"read_error:{e}"

    # try utf-8, then latin-1
    try:
        text = data.decode("utf-8")
        return text, "utf-8"
    except Exception:
        try:
            text = data.decode("latin-1")
            return text, "latin-1"
        except Exception as e:
            return None, f"decode_error:{e}"


def scan_directory(base_dir: Path, include_content: bool = False, max_content_bytes: int = 1_000_000, relative_base: Path | None = None):
    rows = []
    base_dir = base_dir.expanduser().resolve()
    if relative_base is None:
        relative_base = base_dir

    for p in base_dir.rglob("*"):
        if p.is_file():
            try:
                stat = p.stat()
                rel = p.relative_to(relative_base)
            except Exception:
                rel = p

            entry = {
                "relative_path": str(rel),
                "absolute_path": str(p.resolve()),
                "name": p.name,
                "extension": p.suffix.lower(),
                "size_bytes": stat.st_size if p.exists() else None,
                "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat() if p.exists() else None,
            }

            if include_content:
                # only attempt text read for likely text files
                if is_text_file(p):
                    content, enc = read_text_content(p, max_bytes=max_content_bytes)
                    entry["content"] = content
                    entry["content_encoding_or_reason"] = enc
                else:
                    entry["content_encoding_or_reason"] = "binary_or_contains_nul"

            rows.append(entry)

    df = pd.DataFrame(rows)
    return df


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan directory and export file metadata to CSV")
    parser.add_argument("--input", "-i", required=False, default=os.getcwd(), help="Input directory to scan (default: current working directory)")
    parser.add_argument("--output", "-o", required=False, default="blinkist_files.csv", help="Output CSV path (default: blinkist_files.csv)")
    parser.add_argument("--include-content", action="store_true", help="Attempt to read text content of files (may be slow)")
    parser.add_argument("--max-content-bytes", type=int, default=1_000_000, help="Maximum bytes allowed when reading file content (default 1_000_000)")
    parser.add_argument("--relative-base", help="Base path for relative_path column. Defaults to input directory.")

    args = parser.parse_args(argv)

    base = Path(args.input)
    if not base.exists() or not base.is_dir():
        print(f"Input path does not exist or is not a directory: {base}")
        sys.exit(2)

    rel_base = Path(args.relative_base) if args.relative_base else None

    print(f"Scanning directory: {base}")
    df = scan_directory(base, include_content=args.include_content, max_content_bytes=args.max_content_bytes, relative_base=rel_base)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Save CSV. For large textual content, this may be large; user chose include-content explicitly.
    df.to_csv(out, index=False)
    print(f"Saved {len(df)} records to {out}")


if __name__ == "__main__":
    main()
