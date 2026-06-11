#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

UNDERLINE_BLANK_PATTERN = re.compile(r"<u>(.*?)</u>_+")
CLOZE_PATTERN = re.compile(r"{{([^{}]+)}}")
LEADING_NUMBER_PATTERN = re.compile(r"^\s*\d+\.\s+")
QUESTION_HEADING_PATTERN = re.compile(r"^\s*##\s+(?:Q\d+\s+)?")
METADATA_PATTERN = re.compile(r"^\s*(Category|Description|CodeMode|ImageMaxWidth):")
BLANK_HINT_PATTERN = re.compile(r"//\s*Blank\s*\d+\s*:\s*([A-Za-z0-9_]+)")
INLINE_BLANK_HINT_PATTERN = re.compile(r"//\s*Blank\s*\d+\s*:\s*([^;\s]+)")
STANDALONE_BLANK_HINT_PATTERN = re.compile(
    r"^(?P<indent>\s*)//\s*Blank\s*\d+\s*:\s*(?P<answer>[^;\s]+)(?:\s*;\s*(?P<comment>.*))?\s*$"
)
UNDERSCORE_BLANK_PATTERN = re.compile(r"_{2,}")
TABLE_TAG_PATTERN = re.compile(r"</?(table|tr|th|td)(?:\s+[^>]*)?>", re.IGNORECASE)


def read_text(path: Path) -> str:
    encodings = ("utf-8", "utf-8-sig", "gb18030")
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_common(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = UNDERLINE_BLANK_PATTERN.sub(r"\1", text)
    text = re.sub(r"<tr(?:\s+[^>]*)?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(?:th|td)(?:\s+[^>]*)?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:th|td)>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?table(?:\s+[^>]*)?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("<u>", "").replace("</u>", "")
    text = re.sub(r"_+", "", text)
    text = re.sub(r"`+", "", text)
    text = re.sub(r"\*\*?", "", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = CLOZE_PATTERN.sub(lambda m: m.group(1).split("|", 1)[0].strip(), text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def source_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_code = False
    pending_answer: str | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.rstrip()
        if stripped.strip().startswith("```"):
            in_code = not in_code
            continue
        if METADATA_PATTERN.match(stripped):
            continue
        candidate = stripped
        if in_code:
            standalone_hint = STANDALONE_BLANK_HINT_PATTERN.match(candidate)
            if standalone_hint:
                pending_answer = standalone_hint.group("answer").strip()
                comment = standalone_hint.group("comment")
                if comment:
                    normalized_comment = normalize_common(f"// {comment}")
                    if normalized_comment:
                        lines.append(normalized_comment)
                continue
        blank_hint = INLINE_BLANK_HINT_PATTERN.search(candidate)
        if blank_hint:
            candidate = INLINE_BLANK_HINT_PATTERN.sub("", candidate)
            candidate = UNDERSCORE_BLANK_PATTERN.sub(blank_hint.group(1), candidate, count=1)
        elif in_code and pending_answer and UNDERSCORE_BLANK_PATTERN.search(candidate):
            candidate = UNDERSCORE_BLANK_PATTERN.sub(pending_answer, candidate, count=1)
            pending_answer = None
        if not in_code:
            candidate = LEADING_NUMBER_PATTERN.sub("", candidate)
            candidate = QUESTION_HEADING_PATTERN.sub("", candidate)
            candidate = candidate.lstrip("- ").strip()
        candidate = normalize_common(candidate)
        if not candidate:
            continue
        lines.append(candidate)
    return lines


def html_to_text(text: str) -> str:
    text = re.sub(r"</(p|div|pre|li|h\d|br)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<tr(?:\s+[^>]*)?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(?:th|td)(?:\s+[^>]*)?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:th|td)>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?table(?:\s+[^>]*)?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def build_corpus(markdown_text: str, html_text: str) -> str:
    combined = "\n".join([markdown_text, html_to_text(html_text)])
    return normalize_common(combined)


def missing_lines(source_text: str, markdown_text: str, html_text: str) -> list[str]:
    corpus = build_corpus(markdown_text, html_text)
    missing: list[str] = []
    seen_folded: set[str] = set()
    for line in source_lines(source_text):
        folded = line.casefold()
        if folded in seen_folded:
            continue
        seen_folded.add(folded)
        if line not in corpus and line not in missing:
            missing.append(line)
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether generated Learning Mall Markdown/HTML dropped content from the source."
    )
    parser.add_argument("source", type=Path, help="Original source file or extracted draft.")
    parser.add_argument("--markdown", required=True, type=Path, help="Generated Learning Mall Markdown.")
    parser.add_argument("--html", required=True, type=Path, help="Generated preview HTML.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.source.expanduser()
    markdown_path = args.markdown.expanduser()
    html_path = args.html.expanduser()
    if not source_path.is_absolute():
        source_path = Path.cwd() / source_path
    if not markdown_path.is_absolute():
        markdown_path = Path.cwd() / markdown_path
    if not html_path.is_absolute():
        html_path = Path.cwd() / html_path

    for path in (source_path, markdown_path, html_path):
        if not path.exists():
            print(f"Input not found: {path}", file=sys.stderr)
            return 1

    source_text = read_text(source_path)
    markdown_text = read_text(markdown_path)
    html_text = read_text(html_path)
    missing = missing_lines(source_text, markdown_text, html_text)

    if not missing:
        print("No missing lines detected.")
        return 0

    print("Potentially missing lines:")
    for line in missing:
        print(f"- {line}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
