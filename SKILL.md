---
name: learning-mall-helper
description: Convert source material or finalized Learning Mall Markdown into Moodle XML import files and HTML preview files for Learning Mall. Use when Codex needs to ingest DOCX, PDF, Markdown, or text quiz sources, normalize them into the local Learning Mall Markdown schema, exclude requested sections, pad cloze blanks, render XML/HTML, or run fidelity checks.
---

# LearningMallHelper

Use this skill as the source-to-deliverables workflow for Learning Mall quiz work.

## Workflow

1. Identify the source type.
   - For `.md`, `.markdown`, or `.txt`, read the file directly unless formatting is messy.
   - For `.docx` or `.pdf`, run `scripts/extract_source.py` to produce an editable Markdown-like draft.
   - For legacy `.doc`, convert it to `.docx` or `.pdf` first.

2. Extract source text when needed.
   - Run `python scripts/extract_source.py <input-file> --output <source-draft.md>`.
   - DOCX, Markdown, and text extraction use the Python standard library.
   - PDF extraction requires `pypdf`; if unavailable, run through `uv`, for example:
     `uv run --with pypdf python scripts/extract_source.py <input-file.pdf> --output <source-draft.md>`.
   - Treat extracted text as source material, not final quiz Markdown.

3. Rewrite the draft into Learning Mall Markdown.
   - Read `references/learningmall-format.md` before authoring final output.
   - Keep only supported metadata: `Category`, `Description`, `CodeMode`, `ImageMaxWidth`.
   - Start every question with `## <title>`.
   - Use `Type: Cloze` with `{{answer}}` or `{{answer1|answer2}}` placeholders for fill-in-the-blank questions.
   - Use `Type: CodeRunner` with `CodeRunnerType: java_program` only for Java programming questions with starter code, reference answer, and tests.
   - When generating CodeRunner questions directly, include at least 5 testcases total. Mark exactly 2 usual-case tests as `Testcase: example`; keep edge cases hidden.
   - When the user provides a CodeRunner template, preserve the template's structure and visible/hidden testcase choices, but still review the starter code, reference answer, and tests for syntax consistency, expected outputs, edge coverage, and alignment with the prompt.
   - Use `- [x]` and `- [ ]` only for multiple-choice questions with explicit correct choices.
   - Use `Type: Description` only for ungraded explanatory blocks.
   - Preserve code blocks, source wording, and local image references whenever they matter.
   - Exclude sections the user explicitly asks to omit.

4. Save the editable Learning Mall Markdown as the canonical artifact.
   - Keep this file even when the user mainly wants XML, because it is the source of truth for later edits.

5. Render final deliverables with this skill's command.
   - Run `scripts/convert <final-markdown> --xml <quiz.xml> --html <preview.html> --pad-cloze --padded-markdown <padded.md>`.
   - The XML is the Learning Mall import artifact.
   - The HTML is the preview artifact.
   - The padded Markdown is a render-source artifact; keep the unpadded Markdown as the editable canonical source.

6. Check fidelity and iterate when the source is not trivial.
   - Run `python scripts/check_fidelity.py <source-or-draft> --markdown <final-markdown> --html <preview.html>`.
   - Review reported missing lines manually; the checker is conservative and can flag harmless formatting changes.
   - Patch the Learning Mall Markdown, rerender, and recheck until the source content needed for the requested scope is represented.

## Commands And Scripts

- `scripts/convert`: Convert finalized Learning Mall Markdown into Moodle XML and HTML preview files. Supports `--xml`, `--html`, `--pretty-xml`, `--pad-cloze`, `--padded-markdown`, and `--in-place`.
- `scripts/extract_source.py`: Extract `.docx`, `.pdf`, `.md`, `.markdown`, or `.txt` into a Markdown-like working draft.
- `scripts/pad_cloze_answers.py`: Append zero-score 40-character random alphanumeric decoy answers to cloze placeholders.
- `scripts/render_outputs.py`: Local renderer used by `convert`.
- `scripts/check_fidelity.py`: Compare source text against generated Markdown and preview HTML for potentially dropped content.

## Rendering Engine

Use this skill's standalone renderer. Do not import parser, preview, or helper code from external LearningMall repositories.
