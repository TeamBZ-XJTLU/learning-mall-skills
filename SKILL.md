---
name: learning-mall-skills
description: Convert source material or finalized Learning Mall Markdown into Moodle XML import files and HTML preview files for Learning Mall. Use when Codex needs to ingest DOCX, PDF, Markdown, or text quiz sources, normalize them into the local Learning Mall Markdown schema, exclude requested sections, pad cloze blanks, render XML/HTML, or run fidelity checks.
---

# LearningMallSkills

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

3. Identify the included question sections and confirm their categories before converting to Learning Mall-compatible Moodle XML.
   - Inspect the source first so the category request reflects its sections and question types. Exclude sections the user asked to omit; do not treat answer keys as question sections.
   - For a single section, ask: "What category name should I use for the Learning Mall question bank?"
   - For multiple sections, including documents with separate MCQ and fill-in-the-blank sections, ask for a category name for each section in one message. List each section by its source heading and question type, with question numbers or ranges when available. For example: "What category name should I use for each section: Part 1 - MCQs (1-10), and Part 2 - Fill-in-the-blank (11-20)?"
   - Preserve the source's section boundaries, even when multiple sections share a question type. If question types are mixed without explicit sections, group questions by type for the category request.
   - Use categories already explicitly supplied for the relevant sections without asking again; ask only for missing mappings. A single supplied category does not automatically apply to every section unless the user says so. The user may explicitly choose the same category for multiple sections.
   - Wait for the required category answers before generating XML, even if the source Markdown already contains categories. Do not invent categories, silently reuse existing ones, or omit them from XML.
   - Set each section's canonical Markdown `Category` metadata to the user's choice. For a category name, use `Category: $course$/top/<category-name>`; preserve a full category path if the user supplies one.

4. Rewrite the draft into Learning Mall Markdown.
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

5. Save the editable Learning Mall Markdown as the canonical artifact.
   - Keep this file even when the user mainly wants XML, because it is the source of truth for later edits.
   - For multiple sections, save a separate canonical Markdown file for each section with its confirmed category. The renderer supports one top-of-file `Category` per file; do not insert category changes between questions.

6. Render final deliverables with this skill's command.
   - Before rendering XML, verify that each section's `Category` matches the user's section-to-category mapping.
   - Run `scripts/convert <final-markdown> --xml <quiz.xml> --html <preview.html> --pad-cloze --padded-markdown <padded.md>`.
   - For multiple sections, run the command separately for each section and deliver clearly named XML, preview, and Markdown files, identifying which category each XML imports into.
   - The XML is the Learning Mall import artifact.
   - The HTML is the preview artifact.
   - The padded Markdown is a render-source artifact; keep the unpadded Markdown as the editable canonical source.

7. Check fidelity and iterate when the source is not trivial.
   - Run `python scripts/check_fidelity.py <source-or-draft> --markdown <final-markdown> --html <preview.html>`.
   - Review reported missing lines manually; the checker is conservative and can flag harmless formatting changes.
   - For multiple sections, check each against its corresponding source section and verify that all included questions are represented exactly once across the deliverables.
   - Patch the Learning Mall Markdown, rerender, and recheck until the source content needed for the requested scope is represented.

## Commands And Scripts

- `scripts/convert`: Convert finalized Learning Mall Markdown into Moodle XML and HTML preview files. Supports `--xml`, `--html`, `--pretty-xml`, `--pad-cloze`, `--padded-markdown`, and `--in-place`.
- `scripts/extract_source.py`: Extract `.docx`, `.pdf`, `.md`, `.markdown`, or `.txt` into a Markdown-like working draft.
- `scripts/pad_cloze_answers.py`: Append zero-score 40-character random alphanumeric decoy answers to cloze placeholders.
- `scripts/render_outputs.py`: Local renderer used by `convert`.
- `scripts/check_fidelity.py`: Compare source text against generated Markdown and preview HTML for potentially dropped content.

## Rendering Engine

Use this skill's standalone renderer. Do not import parser, preview, or helper code from external LearningMall repositories.
