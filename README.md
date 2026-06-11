# LearningMall Skills

Codex skill repository for generating Learning Mall quiz deliverables. The main skill is `learning-mall-skills`, a self-contained workflow for turning source material or Learning Mall Markdown into Moodle XML import files and HTML previews.

## Contents

```text
learning-mall-skills/
├── SKILL.md
├── agents/openai.yaml
├── references/learningmall-format.md
└── scripts/
    ├── check_fidelity.py
    ├── convert
    ├── extract_source.py
    ├── pad_cloze_answers.py
    └── render_outputs.py
```

## Capabilities

- Extract source text from `.docx`, `.md`, `.markdown`, `.txt`, and optionally `.pdf`.
- Author Learning Mall Markdown for multiple-choice, cloze, description, and CodeRunner Java questions.
- Convert Learning Mall Markdown into Moodle XML plus HTML preview.
- Pad cloze answers with zero-score decoys so blank width does not reveal answer length.
- Run a conservative fidelity check against source text.
- Generate CodeRunner questions with `coderunnertype` set to `java_program`.

## Quick Start

Render a finalized Learning Mall Markdown file:

```bash
learning-mall-skills/scripts/convert quiz.learningmall.md \
  --xml quiz.xml \
  --html quiz.preview.html \
  --pretty-xml
```

For final cloze delivery, keep an editable source Markdown and render from a padded copy:

```bash
learning-mall-skills/scripts/convert quiz.learningmall.md \
  --padded-markdown quiz.padded.learningmall.md \
  --xml quiz.xml \
  --html quiz.preview.html \
  --pretty-xml \
  --pad-cloze
```

## Source Extraction

Extract a DOCX source into a Markdown-like draft:

```bash
python learning-mall-skills/scripts/extract_source.py source.docx \
  --output source.extracted.md
```

DOCX, Markdown, and text extraction use the Python standard library. PDF extraction requires `pypdf`:

```bash
uv run --with pypdf python learning-mall-skills/scripts/extract_source.py source.pdf \
  --output source.extracted.md
```

## Markdown Format

See [learningmall-format.md](learning-mall-skills/references/learningmall-format.md) for the supported schema.

Supported question types:

- Multiple choice: checkbox answers with `- [x]` and `- [ ]`.
- Cloze: `Type: Cloze` with placeholders such as `{{answer}}`.
- Description: `Type: Description` for ungraded text.
- CodeRunner Java: `Type: CodeRunner` with `CodeRunnerType: java_program`.

CodeRunner generation policy:

- Use only `java_program`.
- Directly generated CodeRunner questions should include at least 5 testcases.
- Exactly 2 usual-case testcases should be marked `Testcase: example`.
- Edge cases should be hidden.
- If a user provides a template, preserve its structure and visible/hidden testcase choices, but still check starter code, reference answer, expected outputs, and edge coverage.

## Validation

Validate the skill folder:

```bash
uv run --with pyyaml python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  [skill folder path]
```

Run a fidelity check after rendering:

```bash
python learning-mall-skills/scripts/check_fidelity.py source.extracted.md \
  --markdown quiz.learningmall.md \
  --html quiz.preview.html
```

## Skill Entry Point

Codex should load [SKILL.md](learning-mall-skills/SKILL.md) when asked to convert Learning Mall materials, create quiz Markdown, render Moodle XML, build previews, or generate CodeRunner Java questions.
