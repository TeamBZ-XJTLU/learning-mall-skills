#!/usr/bin/env python3
"""Extract source documents into a Markdown-like working draft."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

WORD_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


def read_text_file(path: Path) -> str:
    encodings = ("utf-8", "utf-8-sig", "gb18030")
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{{{WORD_NS['w']}}}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{{{WORD_NS['w']}}}tab":
            parts.append("\t")
        elif node.tag == f"{{{WORD_NS['w']}}}br":
            parts.append("\n")
    return "".join(parts).strip()


def paragraph_style(paragraph: ET.Element) -> str:
    p_style = paragraph.find("./w:pPr/w:pStyle", WORD_NS)
    if p_style is None:
        return ""
    return p_style.attrib.get(f"{{{WORD_NS['w']}}}val", "").lower()


def render_paragraph(paragraph: ET.Element) -> str:
    text = paragraph_text(paragraph)
    if not text:
        return ""
    style = paragraph_style(paragraph)
    if style.startswith("heading"):
        match = re.search(r"(\d+)", style)
        level = int(match.group(1)) if match else 1
        level = max(1, min(level, 6))
        return f"{'#' * level} {text}"
    if "listparagraph" in style or "bullet" in style:
        return f"- {text}"
    return text


def render_table(table: ET.Element) -> str:
    rows: list[list[str]] = []
    for row in table.findall("./w:tr", WORD_NS):
        values: list[str] = []
        for cell in row.findall("./w:tc", WORD_NS):
            cell_parts = [paragraph_text(p) for p in cell.findall(".//w:p", WORD_NS)]
            values.append(" ".join(part for part in cell_parts if part).strip())
        if values:
            rows.append(values)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    body = normalized[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    body = root.find("./w:body", WORD_NS)
    if body is None:
        raise ValueError("DOCX document body not found.")

    parts = [f"# Extracted source from {path.name}", "", f"Source format: {path.suffix.lower()}"]
    for child in body:
        if child.tag == f"{{{WORD_NS['w']}}}p":
            rendered = render_paragraph(child)
        elif child.tag == f"{{{WORD_NS['w']}}}tbl":
            rendered = render_table(child)
        else:
            rendered = ""
        if rendered:
            parts.extend(["", rendered])
    return normalize_text("\n".join(parts))


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise RuntimeError("PDF extraction requires pypdf. Run with: uv run --with pypdf python scripts/extract_source.py ...") from exc

    reader = PdfReader(str(path))
    parts = [f"# Extracted source from {path.name}", "", f"Source format: {path.suffix.lower()}"]
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        cleaned = normalize_text(text) if text else "[No extractable text on this page]\n"
        parts.extend(["", f"## Page {index}", "", cleaned.rstrip("\n")])
    return normalize_text("\n".join(parts))


def extract_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        return normalize_text(read_text_file(path))
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".doc":
        raise ValueError("Legacy .doc files are not supported directly. Convert the file to .docx or .pdf first.")
    raise ValueError(f"Unsupported file type: {suffix or '[no extension]'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract .docx, .pdf, .md, .markdown, or .txt into a Markdown-like working draft."
    )
    parser.add_argument("input", type=Path, help="Source file to extract.")
    parser.add_argument("--output", type=Path, help="Optional output file. Defaults to stdout.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser()
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    try:
        extracted = extract_source(input_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    if args.output:
        output_path = args.output.expanduser()
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(extracted, encoding="utf-8")
    else:
        sys.stdout.write(extracted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
