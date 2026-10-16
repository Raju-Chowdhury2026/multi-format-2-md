"""Convert one file from the command line.

    py -3 -m app.cli report.pdf -o report.md
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from app.converter import Conversion, ConversionError, convert_bytes
from app.store import ensure_schema, save_conversion


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a file to Markdown and report token savings."
    )
    parser.add_argument("path", help="File to convert")
    parser.add_argument("-o", "--output", help="Write Markdown to this path")
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not store the conversion in history",
    )
    args = parser.parse_args(argv)

    source = Path(args.path)
    if not source.is_file():
        print(f"File not found: {source}", file=sys.stderr)
        return 1
    try:
        result = convert_bytes(source.name, source.read_bytes())
    except ConversionError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(result.markdown, encoding="utf-8")
        _print_stats(result)
    else:
        print(result.markdown)
        _print_stats(result, file=sys.stderr)

    if not args.no_save:
        _save(result)
    return 0


def _print_stats(result: Conversion, file=None) -> None:
    stream = file or sys.stdout
    print(result.filename, file=stream)
    if result.source_tokens is None:
        print("Source tokens: none (no text baseline)", file=stream)
    else:
        print(f"Source tokens: {result.source_tokens:,}", file=stream)
    print(f"Markdown tokens: {result.markdown_tokens:,}", file=stream)
    if result.savings_pct is None:
        print("Savings: context captured", file=stream)
    else:
        print(f"Savings: {result.savings_pct}%", file=stream)
    if result.warning:
        print(f"Warning: {result.warning}", file=stream)


def _save(result: Conversion) -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        ensure_schema()
        save_conversion(result)
    except Exception:
        logging.getLogger("mdcreator").exception("Could not save conversion history")
        print("Warning: the conversion was not saved to history.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
