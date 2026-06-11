#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import secrets
import string
import sys
from pathlib import Path

PLACEHOLDER_PATTERN = re.compile(r"{{([^{}]+)}}")
DECOY_PATTERN = re.compile(r"^[A-Za-z0-9]{40}$")
ZERO_SCORE_DECOY_PATTERN = re.compile(r"^0%:([A-Za-z0-9]{40})$")
ALPHABET = string.ascii_letters + string.digits


def generate_decoy(length: int = 40) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def pad_placeholders(text: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        parts = [part.strip() for part in match.group(1).split("|")]
        if any(ZERO_SCORE_DECOY_PATTERN.fullmatch(part) for part in parts[1:]):
            return match.group(0)

        changed = False
        for idx in range(1, len(parts)):
            if DECOY_PATTERN.fullmatch(parts[idx]):
                parts[idx] = f"0%:{parts[idx]}"
                changed = True

        if not changed:
            parts.append(f"0%:{generate_decoy()}")

        count += 1
        return "{{" + "|".join(parts) + "}}"

    return PLACEHOLDER_PATTERN.sub(replace, text), count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Append a zero-score 40-character random alphanumeric decoy answer "
            "to each cloze placeholder."
        )
    )
    parser.add_argument("input", type=Path, help="Learning Mall Markdown file.")
    parser.add_argument("--output", type=Path, help="Output path. Defaults to stdout unless --in-place is set.")
    parser.add_argument("--in-place", action="store_true", help="Rewrite the input file in place.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser()
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1
    if args.in_place and args.output:
        print("Use either --in-place or --output, not both.", file=sys.stderr)
        return 1

    original = input_path.read_text(encoding="utf-8")
    padded, count = pad_placeholders(original)

    if args.in_place:
        input_path.write_text(padded, encoding="utf-8")
        print(f"Updated {input_path} with {count} padded cloze placeholders")
        return 0

    if args.output:
        output_path = args.output.expanduser()
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(padded, encoding="utf-8")
        print(f"Wrote {output_path} with {count} padded cloze placeholders")
        return 0

    sys.stdout.write(padded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
