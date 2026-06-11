#!/usr/bin/env python3
"""Standalone Learning Mall Markdown to Moodle XML and preview HTML renderer."""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
ANSWER_PATTERN = re.compile(r"^- \[(x|\s)\]\s*(.*)$", re.IGNORECASE)
CLOZE_PLACEHOLDER_PATTERN = re.compile(r"{{([^{}]+)}}")
CLOZE_FIELD_PATTERN = re.compile(r"{\d+\s*:SAC:[^}]+}")
SCORED_CLOZE_ALTERNATE_PATTERN = re.compile(r"^(?P<fraction>\d+)%:(?P<answer>.+)$")
CODE_TOKEN_PATTERN = re.compile(
    r"\ue000\d+\ue001|//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|@\w+|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b|.",
    re.DOTALL,
)
JAVA_KEYWORDS = {
    "abstract",
    "assert",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "default",
    "do",
    "else",
    "enum",
    "extends",
    "final",
    "finally",
    "for",
    "goto",
    "if",
    "implements",
    "import",
    "instanceof",
    "interface",
    "new",
    "package",
    "private",
    "protected",
    "public",
    "return",
    "static",
    "strictfp",
    "super",
    "switch",
    "synchronized",
    "this",
    "throw",
    "throws",
    "transient",
    "try",
    "void",
    "volatile",
    "while",
}
JAVA_TYPES_AND_LITERALS = {
    "boolean",
    "byte",
    "char",
    "double",
    "false",
    "float",
    "int",
    "long",
    "null",
    "short",
    "true",
}


@dataclass
class EmbeddedFile:
    name: str
    content: bytes
    path: str = "/"
    encoding: str = "base64"


@dataclass
class Answer:
    html: str
    fraction: int
    files: list[EmbeddedFile] = field(default_factory=list)


@dataclass
class Question:
    qtype: str
    name: str
    html: str
    defaultgrade: float = 1.0
    penalty: float = 0.3333333
    answers: list[Answer] = field(default_factory=list)
    files: list[EmbeddedFile] = field(default_factory=list)
    coderunnertype: str = "java_program"
    answerpreload: str = ""
    coderunner_answer: str = ""
    template: str = ""
    answerboxlines: int = 18
    answerboxcolumns: int = 100
    testcases: list["CodeRunnerTestcase"] = field(default_factory=list)


@dataclass
class CodeRunnerTestcase:
    testcode: str
    expected: str
    stdin: str = ""
    extra: str = ""
    display: str = "SHOW"
    useasexample: bool = False
    mark: float = 1.0


def resolve_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def xml_escape(value: str) -> str:
    return html.escape(value, quote=True)


def cdata(value: str) -> str:
    return "<![CDATA[" + value.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def text_node(tag: str, value: str, indent: str = "      ") -> str:
    return f"{indent}<{tag}>{xml_escape(value)}</{tag}>"


def file_xml(file: EmbeddedFile, indent: str = "      ") -> str:
    payload = base64.b64encode(file.content).decode("ascii")
    return (
        f'{indent}<file name="{xml_escape(file.name)}" path="{xml_escape(file.path)}" '
        f'encoding="{xml_escape(file.encoding)}">{payload}</file>'
    )


def markdown_inline(text: str) -> str:
    placeholders: list[str] = []

    def stash_cloze(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"@@CLOZE_{len(placeholders) - 1}@@"

    text = CLOZE_FIELD_PATTERN.sub(stash_cloze, text)
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    for index, placeholder in enumerate(placeholders):
        text = text.replace(f"@@CLOZE_{index}@@", html.escape(placeholder))
    return text


def highlight_code(code: str, language: str = "") -> str:
    """Return inline-styled HTML for small Java-oriented code snippets."""
    placeholders: list[str] = []

    def stash_cloze(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\ue000{len(placeholders) - 1}\ue001"

    protected = CLOZE_FIELD_PATTERN.sub(stash_cloze, code)
    language = language.lower()
    if language and language not in {"java", "text", "txt"}:
        return html.escape(protected)

    rendered: list[str] = []
    for token_match in CODE_TOKEN_PATTERN.finditer(protected):
        token = token_match.group(0)
        if token.startswith("\ue000") and token.endswith("\ue001"):
            index = int(token[1:-1])
            rendered.append(html.escape(placeholders[index]))
        elif token.startswith("//") or token.startswith("/*"):
            rendered.append(f'<span style="color: #6A737D;">{html.escape(token)}</span>')
        elif token.startswith('"') or token.startswith("'"):
            rendered.append(f'<span style="color: #BA2121;">{html.escape(token)}</span>')
        elif token.startswith("@"):
            rendered.append(f'<span style="color: #795E26;">{html.escape(token)}</span>')
        elif re.fullmatch(r"\d+(?:\.\d+)?", token):
            rendered.append(f'<span style="color: #40A070;">{html.escape(token)}</span>')
        elif token in JAVA_KEYWORDS:
            rendered.append(f'<span style="color: #007020; font-weight: bold;">{html.escape(token)}</span>')
        elif token in JAVA_TYPES_AND_LITERALS:
            rendered.append(f'<span style="color: #902000;">{html.escape(token)}</span>')
        else:
            rendered.append(html.escape(token))
    return "".join(rendered)


def render_code_block(code: str, language: str = "") -> str:
    lang_class = f' class="language-{html.escape(language)}"' if language else ""
    highlighted = highlight_code(code, language)
    return (
        '<div class="highlight" style="background: #f8fafc;">'
        f'<pre style="line-height: 1.55; margin: 0;"><code{lang_class}>{highlighted}</code></pre>'
        "</div>"
    )


def read_image(path_str: str, base_dir: Path) -> EmbeddedFile:
    raw_path = Path(path_str.strip())
    image_path = raw_path if raw_path.is_absolute() else base_dir / raw_path
    return EmbeddedFile(name=image_path.name, content=image_path.read_bytes())


def replace_images(text: str, base_dir: Path, image_max_width: int | None) -> tuple[str, list[EmbeddedFile]]:
    files: list[EmbeddedFile] = []

    def replace(match: re.Match[str]) -> str:
        alt = html.escape(match.group(1))
        path_str = match.group(2).strip()
        file = read_image(path_str, base_dir)
        files.append(file)
        style = f' style="max-width:{image_max_width}px; height:auto;"' if image_max_width else ""
        return f'<img src="@@PLUGINFILE@@/{html.escape(file.name)}" alt="{alt}"{style} />'

    return IMAGE_PATTERN.sub(replace, text), files


def render_plain_blocks(text: str, base_dir: Path, image_max_width: int | None) -> tuple[str, list[EmbeddedFile]]:
    text, files = replace_images(text, base_dir, image_max_width)
    lines = text.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_code = False
    code_language = ""
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            joined = " ".join(line.strip() for line in paragraph if line.strip())
            if joined:
                blocks.append(f"<p>{markdown_inline(joined)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            items = "\n".join(f"<li>{markdown_inline(item)}</li>" for item in list_items)
            blocks.append(f"<ul>\n{items}\n</ul>")
            list_items = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                code = "\n".join(code_lines)
                blocks.append(render_code_block(code, code_language))
                in_code = False
                code_language = ""
                code_lines = []
            else:
                flush_paragraph()
                flush_list()
                in_code = True
                code_language = stripped[3:].strip()
                code_lines = []
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        if stripped.startswith("- ") and not ANSWER_PATTERN.match(stripped):
            flush_paragraph()
            list_items.append(stripped[2:].strip())
            continue

        if "<img " in stripped and stripped.startswith("<img "):
            flush_paragraph()
            flush_list()
            blocks.append(stripped)
            continue

        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    if in_code:
        code = "\n".join(code_lines)
        blocks.append(render_code_block(code, code_language))
    return "\n".join(blocks), files


def convert_cloze_placeholders(md: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        raw = match.group(1).strip()
        parts = [part.strip() for part in raw.split("|") if part.strip()]
        if not parts:
            raise ValueError("Empty cloze placeholder found.")
        answer = f"={parts[0]}"
        alternates: list[str] = []
        for alt in parts[1:]:
            scored = SCORED_CLOZE_ALTERNATE_PATTERN.match(alt)
            if scored:
                fraction = scored.group("fraction")
                alt_answer = scored.group("answer").strip()
                if not alt_answer:
                    raise ValueError("Empty scored cloze alternate found.")
                alternates.append(f"~%{fraction}%{alt_answer}")
            else:
                alternates.append(f"~%100%{alt}")
        return f"{{1:SAC:{answer}{''.join(alternates)}}}"

    return CLOZE_PLACEHOLDER_PATTERN.sub(replace, md), count


def parse_metadata(lines: list[str]) -> tuple[dict[str, str], int]:
    metadata: dict[str, str] = {}
    idx = 0
    while idx < len(lines) and lines[idx].strip():
        line = lines[idx].strip()
        if ":" not in line:
            break
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key not in {"category", "description", "codemode", "imagemaxwidth"}:
            break
        metadata[key] = value.strip()
        idx += 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return metadata, idx


def consume_answer(lines: list[str], start_line: str, start_idx: int) -> tuple[str, int]:
    content_lines = [start_line]
    idx = start_idx
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if line.startswith("## ") or ANSWER_PATTERN.match(stripped):
            break
        if stripped.startswith("```"):
            content_lines.append(line)
            idx += 1
            while idx < len(lines):
                content_lines.append(lines[idx])
                if lines[idx].strip().startswith("```"):
                    idx += 1
                    break
                idx += 1
            continue
        if line.startswith("    ") or line.startswith("\t") or not stripped:
            content_lines.append(line)
            idx += 1
            continue
        break
    return "\n".join(content_lines).strip(), idx


def default_java_template() -> str:
    return """{{ STUDENT_ANSWER }}

public class __tester__ {
    public static void main(String[] args) {
        {{TEST.testcode}}
    }
}"""


def parse_boolish(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "show", "example"}


def parse_testcase_header(value: str) -> tuple[bool, float]:
    useasexample = False
    mark = 1.0
    for token in value.split():
        lowered = token.lower()
        if lowered in {"example", "visible", "show"}:
            useasexample = True
        elif lowered in {"hidden", "hide"}:
            useasexample = False
        elif lowered.startswith("mark="):
            mark = float(token.split("=", 1)[1])
        elif lowered.startswith("useasexample="):
            useasexample = parse_boolish(token.split("=", 1)[1])
    return useasexample, mark


def read_fenced_block(lines: list[str], idx: int) -> tuple[str, int]:
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines) or not lines[idx].strip().startswith("```"):
        raise ValueError("Expected a fenced code block.")
    idx += 1
    captured: list[str] = []
    while idx < len(lines):
        if lines[idx].strip().startswith("```"):
            return "\n".join(captured), idx + 1
        captured.append(lines[idx])
        idx += 1
    raise ValueError("Unterminated fenced code block.")


def parse_coderunner_body(
    title: str,
    body_md: str,
    base_dir: Path,
    image_max_width: int | None,
) -> Question:
    lines = body_md.splitlines()
    prompt_lines: list[str] = []
    coderunnertype = "java_program"
    answerboxlines = 18
    answerboxcolumns = 100
    defaultgrade = 1.0
    answerpreload = ""
    answer = ""
    template = default_java_template()
    testcases: list[CodeRunnerTestcase] = []
    current_test: CodeRunnerTestcase | None = None
    idx = 0

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            prompt_lines.append(line)
            idx += 1
            continue

        if ":" in stripped and not stripped.startswith("```"):
            key, raw_value = stripped.split(":", 1)
            key_lower = key.strip().lower()
            value = raw_value.strip()
            if key_lower == "coderunnertype":
                coderunnertype = value or "java_program"
                idx += 1
                continue
            if key_lower == "answerboxlines":
                answerboxlines = int(value)
                idx += 1
                continue
            if key_lower == "answerboxcolumns":
                answerboxcolumns = int(value)
                idx += 1
                continue
            if key_lower == "defaultgrade":
                defaultgrade = float(value)
                idx += 1
                continue
            if key_lower in {"preload", "answer", "template"}:
                block, idx = read_fenced_block(lines, idx + 1)
                if key_lower == "preload":
                    answerpreload = block
                elif key_lower == "answer":
                    answer = block
                else:
                    template = block
                continue
            if key_lower in {"testcase", "test"}:
                useasexample, mark = parse_testcase_header(value)
                current_test = CodeRunnerTestcase(testcode="", expected="", useasexample=useasexample, mark=mark)
                testcases.append(current_test)
                idx += 1
                continue
            if key_lower in {"testcode", "expected", "stdin", "extra", "display"}:
                if current_test is None:
                    current_test = CodeRunnerTestcase(testcode="", expected="")
                    testcases.append(current_test)
                block, idx = read_fenced_block(lines, idx + 1)
                if key_lower == "testcode":
                    current_test.testcode = block
                elif key_lower == "expected":
                    current_test.expected = block
                elif key_lower == "stdin":
                    current_test.stdin = block
                elif key_lower == "extra":
                    current_test.extra = block
                else:
                    current_test.display = block.strip() or "SHOW"
                continue

        if lowered.startswith("type:"):
            idx += 1
            continue
        prompt_lines.append(line)
        idx += 1

    if coderunnertype != "java_program":
        raise ValueError(f"Unsupported CodeRunnerType '{coderunnertype}'. Only java_program is supported.")
    if not answerpreload:
        raise ValueError(f"CodeRunner question '{title}' is missing a Preload block.")
    if not answer:
        raise ValueError(f"CodeRunner question '{title}' is missing an Answer block.")
    if not testcases:
        raise ValueError(f"CodeRunner question '{title}' must include at least one Testcase.")
    for index, testcase in enumerate(testcases, start=1):
        if not testcase.testcode:
            raise ValueError(f"CodeRunner question '{title}' testcase {index} is missing TestCode.")
        if testcase.expected == "":
            raise ValueError(f"CodeRunner question '{title}' testcase {index} is missing Expected.")

    prompt_md = "\n".join(prompt_lines).strip()
    body_html, files = render_plain_blocks(prompt_md, base_dir, image_max_width)
    return Question(
        qtype="coderunner",
        name=title.strip(),
        html=body_html,
        defaultgrade=defaultgrade,
        penalty=0.0,
        files=files,
        coderunnertype=coderunnertype,
        answerpreload=answerpreload,
        coderunner_answer=answer,
        template=template,
        answerboxlines=answerboxlines,
        answerboxcolumns=answerboxcolumns,
        testcases=testcases,
    )


def parse_markdown(md_text: str, base_dir: Path) -> tuple[list[Question], str | None]:
    lines = md_text.splitlines()
    metadata, idx = parse_metadata(lines)
    category = metadata.get("category")
    default_image_max_width: int | None = None
    if metadata.get("imagemaxwidth"):
        try:
            default_image_max_width = int(metadata["imagemaxwidth"])
        except ValueError as exc:
            raise ValueError("ImageMaxWidth must be an integer.") from exc

    parsed_questions: list[Question] = []
    current_title = ""
    current_body: list[str] = []
    current_answers: list[Answer] = []
    current_type = "multichoice"
    current_image_max_width = default_image_max_width

    def flush_question() -> None:
        nonlocal current_title, current_body, current_answers, current_type, current_image_max_width
        if not current_title:
            return
        body_md = "\n".join(current_body).strip()
        is_cloze = current_type == "cloze" or (not current_answers and CLOZE_PLACEHOLDER_PATTERN.search(body_md))
        if current_type == "coderunner":
            parsed_questions.append(
                parse_coderunner_body(
                    current_title,
                    body_md,
                    base_dir,
                    current_image_max_width,
                )
            )
        elif is_cloze:
            cloze_md, blanks = convert_cloze_placeholders(body_md)
            body_html, files = render_plain_blocks(cloze_md, base_dir, current_image_max_width)
            parsed_questions.append(
                Question(
                    qtype="cloze",
                    name=current_title.strip(),
                    html=body_html,
                    defaultgrade=float(blanks or 1),
                    files=files,
                )
            )
        elif current_type == "description":
            body_html, files = render_plain_blocks(body_md, base_dir, current_image_max_width)
            parsed_questions.append(
                Question(
                    qtype="description",
                    name=current_title.strip(),
                    html=body_html,
                    defaultgrade=0.0,
                    penalty=0.0,
                    files=files,
                )
            )
        else:
            if not current_answers:
                raise ValueError(f"Question '{current_title}' has no answers.")
            body_html, files = render_plain_blocks(body_md, base_dir, current_image_max_width)
            parsed_questions.append(
                Question(
                    qtype="multichoice",
                    name=current_title.strip(),
                    html=body_html,
                    answers=current_answers,
                    files=files,
                )
            )

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        answer_match = ANSWER_PATTERN.match(stripped)
        if line.startswith("## "):
            flush_question()
            current_title = line[3:].strip()
            current_body = []
            current_answers = []
            current_type = "multichoice"
            current_image_max_width = default_image_max_width
        elif answer_match and current_type != "cloze":
            mark = answer_match.group(1).lower()
            answer_md, next_idx = consume_answer(lines, answer_match.group(2).strip(), idx + 1)
            answer_html, answer_files = render_plain_blocks(answer_md, base_dir, current_image_max_width)
            current_answers.append(Answer(html=answer_html, fraction=100 if mark == "x" else 0, files=answer_files))
            idx = next_idx
            continue
        elif stripped.lower().startswith("type:"):
            raw_type = stripped.split(":", 1)[1].strip().lower()
            current_type = "coderunner" if raw_type in {"coderunner", "code runner"} else raw_type
            if current_type == "coderunner":
                current_body.append(line)
        elif stripped.lower().startswith("imagemaxwidth:"):
            raw = stripped.split(":", 1)[1].strip()
            current_image_max_width = int(raw) if raw else default_image_max_width
        else:
            current_body.append(line)
        idx += 1

    flush_question()
    if not parsed_questions:
        raise ValueError("No questions parsed from Markdown.")

    questions: list[Question] = []
    if metadata.get("description"):
        desc_html, desc_files = render_plain_blocks(metadata["description"], base_dir, default_image_max_width)
        questions.append(Question(qtype="description", name="Description", html=desc_html, defaultgrade=0.0, penalty=0.0, files=desc_files))
    questions.extend(parsed_questions)
    return questions, category


def question_xml(question: Question, indent: str = "  ") -> str:
    lines = [f'{indent}<question type="{question.qtype}">']
    lines.append(f"{indent}  <name>")
    lines.append(text_node("text", question.name, indent=f"{indent}    "))
    lines.append(f"{indent}  </name>")
    lines.append(f'{indent}  <questiontext format="html">')
    lines.append(f"{indent}    <text>{cdata(question.html)}</text>")
    for file in question.files:
        lines.append(file_xml(file, indent=f"{indent}    "))
    lines.append(f"{indent}  </questiontext>")
    lines.append(f'{indent}  <generalfeedback format="html">')
    lines.append(f"{indent}    <text>{cdata('')}</text>")
    lines.append(f"{indent}  </generalfeedback>")
    lines.append(text_node("defaultgrade", f"{question.defaultgrade:.7f}", indent=f"{indent}  "))
    lines.append(text_node("penalty", f"{question.penalty:.7f}", indent=f"{indent}  "))
    lines.append(text_node("hidden", "0", indent=f"{indent}  "))
    lines.append(text_node("idnumber", "", indent=f"{indent}  "))

    if question.qtype == "coderunner":
        lines.extend(coderunner_xml_fields(question, indent=indent))
    elif question.qtype == "multichoice":
        correct_count = sum(1 for answer in question.answers if answer.fraction > 0)
        lines.append(text_node("single", "true" if correct_count <= 1 else "false", indent=f"{indent}  "))
        lines.append(text_node("shuffleanswers", "true", indent=f"{indent}  "))
        lines.append(text_node("answernumbering", "abc", indent=f"{indent}  "))
        lines.append(text_node("showstandardinstruction", "1", indent=f"{indent}  "))
        for tag, message in (
            ("correctfeedback", "<p>Your answer is correct.</p>"),
            ("partiallycorrectfeedback", "<p>Your answer is partially correct.</p>"),
            ("incorrectfeedback", "<p>Your answer is incorrect.</p>"),
        ):
            lines.append(f'{indent}  <{tag} format="html">')
            lines.append(f"{indent}    <text>{cdata(message)}</text>")
            lines.append(f"{indent}  </{tag}>")
        lines.append(f"{indent}  <shownumcorrect />")
        for answer in question.answers:
            lines.append(f'{indent}  <answer fraction="{answer.fraction}" format="html">')
            lines.append(f"{indent}    <text>{cdata(answer.html)}</text>")
            for file in answer.files:
                lines.append(file_xml(file, indent=f"{indent}    "))
            lines.append(f'{indent}    <feedback format="html">')
            lines.append(f"{indent}      <text>{cdata('')}</text>")
            lines.append(f"{indent}    </feedback>")
            lines.append(f"{indent}  </answer>")

    lines.append(f"{indent}</question>")
    return "\n".join(lines)


def simple_element(tag: str, value: str, indent: str = "    ") -> str:
    return f"{indent}<{tag}>{xml_escape(value)}</{tag}>"


def coderunner_text_section(tag: str, value: str, indent: str = "      ", use_cdata: bool = False) -> list[str]:
    text = cdata(value) if use_cdata else xml_escape(value)
    return [
        f"{indent}<{tag}>",
        f"{indent}          <text>{text}</text>",
        f"{indent}</{tag}>",
    ]


def coderunner_xml_fields(question: Question, indent: str = "  ") -> list[str]:
    lines: list[str] = []
    field_values = [
        ("coderunnertype", question.coderunnertype),
        ("prototypetype", "0"),
        ("allornothing", "1"),
        ("penaltyregime", "0"),
        ("precheck", "0"),
        ("hidecheck", "0"),
        ("showsource", "0"),
        ("answerboxlines", str(question.answerboxlines)),
        ("answerboxcolumns", str(question.answerboxcolumns)),
    ]
    for tag, value in field_values:
        lines.append(simple_element(tag, value, indent=f"{indent}  "))
    lines.append(f"{indent}  <answerpreload>{cdata(question.answerpreload)}</answerpreload>")
    for tag in ("globalextra", "useace", "resultcolumns"):
        lines.append(simple_element(tag, "", indent=f"{indent}  "))
    lines.append(f"{indent}  <template>{xml_escape(question.template)}</template>")
    for tag in ("iscombinatortemplate", "allowmultiplestdins"):
        lines.append(simple_element(tag, "", indent=f"{indent}  "))
    lines.append(f"{indent}  <answer>{cdata(question.coderunner_answer)}</answer>")
    for tag, value in (
        ("validateonsave", "1"),
        ("testsplitterre", ""),
        ("language", ""),
        ("acelang", ""),
        ("sandbox", ""),
        ("grader", ""),
        ("cputimelimitsecs", ""),
        ("memlimitmb", ""),
        ("sandboxparams", ""),
        ("templateparams", ""),
        ("hoisttemplateparams", "1"),
        ("extractcodefromjson", "1"),
        ("templateparamslang", "None"),
        ("templateparamsevalpertry", "0"),
        ("templateparamsevald", "{}"),
        ("twigall", "0"),
        ("uiplugin", ""),
        ("uiparameters", ""),
        ("attachments", "0"),
        ("attachmentsrequired", "0"),
        ("maxfilesize", "10240"),
        ("filenamesregex", ""),
        ("filenamesexplain", ""),
        ("displayfeedback", "1"),
        ("giveupallowed", "0"),
        ("prototypeextra", ""),
    ):
        lines.append(simple_element(tag, value, indent=f"{indent}  "))
    lines.append(f"{indent}  <testcases>")
    for testcase in question.testcases:
        useasexample = "1" if testcase.useasexample else "0"
        lines.append(
            f'{indent}    <testcase testtype="0" useasexample="{useasexample}" '
            f'hiderestiffail="0" mark="{testcase.mark:.7f}" >'
        )
        lines.extend(coderunner_text_section("testcode", testcase.testcode, indent=f"{indent}    ", use_cdata=True))
        lines.extend(coderunner_text_section("stdin", testcase.stdin, indent=f"{indent}    "))
        lines.extend(coderunner_text_section("expected", testcase.expected, indent=f"{indent}    "))
        lines.extend(coderunner_text_section("extra", testcase.extra, indent=f"{indent}    "))
        lines.extend(coderunner_text_section("display", testcase.display, indent=f"{indent}    "))
        lines.append(f"{indent}    </testcase>")
    lines.append(f"{indent}  </testcases>")
    return lines


def category_xml(category: str, indent: str = "  ") -> str:
    return "\n".join(
        [
            f'{indent}<question type="category">',
            f"{indent}  <category>",
            text_node("text", category, indent=f"{indent}    "),
            f"{indent}  </category>",
            f'{indent}  <info format="html">',
            text_node("text", "", indent=f"{indent}    "),
            f"{indent}  </info>",
            text_node("idnumber", "", indent=f"{indent}  "),
            f"{indent}</question>",
        ]
    )


def render_xml(questions: list[Question], category: str | None, pretty: bool) -> bytes:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<quiz>"]
    if category:
        lines.append(category_xml(category))
    for question in questions:
        lines.append(question_xml(question))
    lines.append("</quiz>")
    xml = "\n".join(lines) if pretty else "".join(line.strip() for line in lines)
    return xml.encode("utf-8")


def plugin_lookup(question: Question) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for file in question.files:
        mime, _ = mimetypes.guess_type(file.name)
        mime = mime or "application/octet-stream"
        uri = f"data:{mime};base64,{base64.b64encode(file.content).decode('ascii')}"
        lookup[f"@@PLUGINFILE@@/{file.name}"] = uri
    return lookup


def cloze_to_preview(html_text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        answer = ""
        parts = raw.split(":SAC:", 1)
        if len(parts) == 2:
            answer_part = parts[1].strip("{}")
            if answer_part.startswith("="):
                answer = answer_part[1:].split("~", 1)[0]
        return f'<span class="cloze-blank">{html.escape(answer or "#")}</span>'

    return CLOZE_FIELD_PATTERN.sub(replace, html_text)


def render_preview(questions: list[Question]) -> str:
    cards: list[str] = []
    for question in questions:
        body = question.html
        for token, uri in plugin_lookup(question).items():
            body = body.replace(token, uri)
        if question.qtype == "cloze":
            body = cloze_to_preview(body)

        if question.qtype == "coderunner":
            visible_tests = [test for test in question.testcases if test.useasexample]
            test_blocks = []
            for index, test in enumerate(visible_tests, start=1):
                test_blocks.append(
                    f'<div class="coderunner-test"><div class="test-title">Example test {index}</div>'
                    f'{render_code_block(test.testcode, "java")}'
                    f'<div class="test-title">Expected</div><pre><code>{html.escape(test.expected)}</code></pre></div>'
                )
            tests_html = "\n".join(test_blocks)
            cards.append(
                f'<div class="card question coderunner"><div class="question-title">{html.escape(question.name)}</div>'
                f'<div class="question-body">{body}</div>'
                f'<div class="coderunner-meta">CodeRunner: {html.escape(question.coderunnertype)}</div>'
                f'<div class="test-title">Preload</div>{render_code_block(question.answerpreload, "java")}'
                f'{tests_html}</div>'
            )
        elif question.qtype == "multichoice":
            answer_rows = []
            for answer in question.answers:
                answer_body = answer.html
                for file in answer.files:
                    mime, _ = mimetypes.guess_type(file.name)
                    mime = mime or "application/octet-stream"
                    answer_body = answer_body.replace(
                        f"@@PLUGINFILE@@/{file.name}",
                        f"data:{mime};base64,{base64.b64encode(file.content).decode('ascii')}",
                    )
                icon = "&#9745;" if answer.fraction > 0 else "&#9744;"
                icon_class = "checked" if answer.fraction > 0 else "unchecked"
                answer_rows.append(
                    f'<div class="answer-row"><span class="choice-icon {icon_class}">{icon}</span>'
                    f'<span class="answer-text">{answer_body}</span></div>'
                )
            answers_html = "\n".join(answer_rows)
            cards.append(
                f'<div class="card question multichoice"><div class="question-title">{html.escape(question.name)}</div>'
                f'<div class="question-body">{body}</div><div class="answers">{answers_html}</div></div>'
            )
        else:
            cards.append(
                f'<div class="card question {question.qtype}"><div class="question-title">{html.escape(question.name)}</div>'
                f'<div class="question-body">{body}</div></div>'
            )

    questions_html = "\n".join(cards) or "<p>No questions to preview.</p>"
    return f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body {{ margin: 0; padding: 24px; background: #f8fafc; color: #0f172a; font-family: "Inter","Segoe UI",system-ui,-apple-system,sans-serif; }}
      .preview {{ max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }}
      .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 18px; box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); }}
      .question-title {{ font-size: 16px; font-weight: 700; margin-bottom: 8px; }}
      .question-body p {{ margin: 0 0 10px; line-height: 1.6; }}
      .highlight {{ margin: 10px 0; border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden; }}
      pre {{ overflow-x: auto; background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; line-height: 1.5; }}
      .highlight pre {{ border: 0; border-radius: 0; background: #f8fafc; }}
      code {{ font-family: "SFMono-Regular", Consolas, monospace; }}
      .answers {{ margin-top: 12px; }}
      .answer-row {{ display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border: 1px solid #e5e7eb; border-radius: 8px; background: #f8fafc; margin-bottom: 8px; line-height: 1.6; }}
      .choice-icon {{ width: 18px; color: #94a3b8; }}
      .choice-icon.checked {{ color: #2563eb; }}
      .answer-text p {{ display: inline; margin: 0; }}
      .cloze-blank {{ padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; min-width: 120px; line-height: 1.4; display: inline-block; vertical-align: middle; }}
      .coderunner-meta {{ margin: 12px 0; color: #475569; font-size: 13px; font-weight: 700; }}
      .test-title {{ margin: 12px 0 6px; font-size: 13px; font-weight: 700; color: #334155; }}
      img {{ max-width: 100%; height: auto; }}
    </style>
  </head>
  <body>
    <div class="preview">
      {questions_html}
    </div>
  </body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render Learning Mall quiz Markdown into Moodle XML and HTML preview."
    )
    parser.add_argument("input", type=Path, help="Final Learning Mall quiz Markdown file.")
    parser.add_argument("--xml", type=Path, required=True, help="Destination XML path.")
    parser.add_argument("--html", type=Path, required=True, help="Destination HTML path.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        help="Directory for resolving relative image paths. Defaults to the Markdown file directory.",
    )
    parser.add_argument("--pretty-xml", action="store_true", help="Pretty-print generated XML.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 1

    try:
        md_text = input_path.read_text(encoding="utf-8")
        base_dir = resolve_path(args.base_dir) if args.base_dir else input_path.parent
        questions, category = parse_markdown(md_text, base_dir)
        xml_bytes = render_xml(questions, category, pretty=args.pretty_xml)
        html_text = render_preview(questions)
    except Exception as exc:  # noqa: BLE001
        print(f"Render failed: {exc}", file=sys.stderr)
        return 1

    xml_path = resolve_path(args.xml)
    html_path = resolve_path(args.html)
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    xml_path.write_bytes(xml_bytes)
    html_path.write_text(html_text, encoding="utf-8")
    print(f"Wrote XML: {xml_path}")
    print(f"Wrote HTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
