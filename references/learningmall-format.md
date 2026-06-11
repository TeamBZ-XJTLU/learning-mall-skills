# Learning Mall Markdown Target

This repository parses a small quiz-oriented Markdown dialect and converts it into Moodle XML.
The skill should normally produce three artifacts:

- an intermediate quiz Markdown file
- a Moodle XML file for Learning Mall import
- an HTML preview file

The quiz Markdown must match this structure closely enough for `scripts/convert` to parse it.
After rendering, the generated Markdown and preview HTML must also be checked back against the source so that no substantive source content is lost during normalization.

## Supported Metadata

Only these top-of-file metadata lines are supported:

```markdown
Category: $course$/top/My Category
Description: Intro text shown above questions
CodeMode: html
ImageMaxWidth: 600
```

Rules:

- Put metadata at the top of the file before the first question.
- Keep one metadata item per line.
- Do not add arbitrary YAML frontmatter or unsupported keys at the top of the quiz file.
- Use `CodeMode: html` or `CodeMode: image`.
- Use `ImageMaxWidth` only with an integer value.

## Question Types

### Multiple Choice

Use this when the source provides a clear prompt and an answer key or an explicitly correct option.

```markdown
## Primary key purpose
What is the primary purpose of a PRIMARY KEY in a relational table?
- [x] Uniquely identify each row
- [ ] Store large text values
- [ ] Improve query caching
```

Rules:

- Start the question with `##`.
- Put the prompt text between the heading and the answer list.
- Mark correct answers with `- [x]`.
- Mark distractors with `- [ ]`.
- This parser expects at least one answer for non-description, non-cloze questions.

### Cloze

Use this for fill-in-the-blank or code-completion exercises.

```markdown
## Loop keyword
Type: Cloze
Complete the sentence: Use {{for}} to repeat the block.
```

Accepted placeholder forms:

- `{{answer}}`
- `{{answer1|answer2}}`
- `{{answer|0%:40CharacterRandomAlnumDecoy...}}`

Rules:

- Prefer cloze when the source already contains blanks or missing tokens.
- Do not add checkbox answers to cloze questions.
- Keep code blocks fenced; this repository can render cloze placeholders inside code.
- Prefer `CodeMode: html` when cloze placeholders appear inside code blocks.
- For Learning Mall delivery, append a 40-character random alphanumeric decoy answer to each blank so the rendered blank width does not reveal the expected answer length.
- Encode that decoy as a zero-score alternate using `0%:` so it expands the blank without being accepted as correct.
- If a blank already has legitimate alternates, append the zero-score decoy after the real alternates.

### Description

Use this for non-graded explanatory content.

```markdown
## Instructions
Type: Description
Read the schema and answer the next three questions.
```

Rules:

- Use description blocks for introductions, reading passages, or material without a reliable answer key.
- Do not add answer checkboxes to description blocks.

### CodeRunner Java Program

Use this for Moodle CodeRunner questions that use `java_program`. Other CodeRunner types are intentionally unsupported.

````markdown
## Number Box
Type: CodeRunner
CodeRunnerType: java_program
AnswerBoxLines: 12
AnswerBoxColumns: 100

Complete the `NumberBox` class so it stores one integer and returns double that value.

```java
class NumberBox {
    private int value;
    // complete the constructor and doubleValue method
}
```

Preload:
```java
class NumberBox {
    private int value;

    public NumberBox(int value) {
        // TO DO
    }

    public int doubleValue() {
        // TO DO
    }
}
```

Answer:
```java
class NumberBox {
    private int value;

    public NumberBox(int value) {
        this.value = value;
    }

    public int doubleValue() {
        return value * 2;
    }
}
```

Testcase: example mark=1
TestCode:
```java
NumberBox box = new NumberBox(7);
System.out.println(box.doubleValue());
```
Expected:
```text
14
```

Testcase: example mark=1
TestCode:
```java
NumberBox box = new NumberBox(3);
System.out.println(box.doubleValue());
```
Expected:
```text
6
```

Testcase: hidden mark=1
TestCode:
```java
NumberBox box = new NumberBox(0);
System.out.println(box.doubleValue());
```
Expected:
```text
0
```

Testcase: hidden mark=1
TestCode:
```java
NumberBox box = new NumberBox(-4);
System.out.println(box.doubleValue());
```
Expected:
```text
-8
```

Testcase: hidden mark=1
TestCode:
```java
NumberBox box = new NumberBox(1000);
System.out.println(box.doubleValue());
```
Expected:
```text
2000
```
````

Rules:

- `Type: CodeRunner` creates `<question type="coderunner">`.
- `CodeRunnerType` must be `java_program`; any other value is rejected.
- `Preload`, `Answer`, and at least one `Testcase` are required.
- Testcases require `TestCode` and `Expected`; optional sections are `Stdin`, `Extra`, and `Display`.
- `Testcase: example` sets `useasexample="1"`; `Testcase: hidden` or no flag sets `useasexample="0"`.
- `mark=<number>` on the testcase line sets the testcase mark.
- When generating CodeRunner questions directly, provide at least 5 testcases total.
- Mark exactly 2 usual-case testcases as examples so students can see representative behavior before submission.
- Put edge cases in hidden testcases. Cover boundaries such as zero, negative values, empty collections, null handling, duplicates, maximum/minimum meaningful values, or branch-specific behavior as applicable to the prompt.
- If the user provides a CodeRunner template, follow the template's visible/hidden testcase structure and field choices. Still check the code and tests: starter code should compile in the CodeRunner wrapper, the reference answer should satisfy every expected output, test cases should align with the prompt, and edge coverage should not be accidentally lost.
- If `Template` is omitted, the renderer uses the standard Java tester template:

```text
{{ STUDENT_ANSWER }}

public class __tester__ {
    public static void main(String[] args) {
        {{TEST.testcode}}
    }
}
```

## Conversion Heuristics

- If the source already contains explicit questions and correct answers, preserve them as multiple-choice or cloze items instead of paraphrasing heavily.
- If the source contains numbered or lettered options, normalize them into `- [x]` and `- [ ]`.
- If the source includes lecture notes plus a few exercises, split the notes into `Type: Description` sections and convert only the clearly gradeable material into questions.
- If the source provides blanks, omitted keywords, or code gaps, convert them into cloze placeholders.
- If the source provides a programming prompt, starter code, reference answer, and test cases, convert it into `Type: CodeRunner` with `CodeRunnerType: java_program`.
- If a source file is already close to the target structure, make the smallest possible edits and validate.
- If a correct answer is missing, do not invent one just to satisfy the parser. Ask the user or fall back to a description block.

## Common Failure Modes

- No blank line after the metadata block is not fatal, but unsupported lines at the top can stop metadata parsing in unexpected places.
- A non-cloze, non-description question without any checkbox answers raises `Question '<title>' has no answers.`
- `ImageMaxWidth` must be an integer.
- Unknown `CodeMode` values are ignored, so use only `html` or `image`.
- Cloze placeholders are only recognized when written as `{{...}}`.
- Content can be lost during conversion when inline comments, explanatory lines, or part of a code block are omitted from the final quiz Markdown.
- Preview checks must cover question body text, code blocks, code comments, list items, and explanatory notes, not just whether XML rendering succeeded.
- Final validation should always use this repository, not a generic Markdown linter.

## Validation Command

Run the local renderer against the final quiz Markdown:

```bash
python learning-mall-skills/scripts/render_outputs.py \
  /path/to/final-quiz.md \
  --xml /tmp/learningmall-check.xml \
  --html /tmp/learningmall-preview.html
```

Success means the file is structurally acceptable to the repository parser and preview renderer.

## Fidelity Loop

After rendering XML and preview HTML, compare the source against the generated artifacts:

```bash
python learning-mall-skills/scripts/check_fidelity.py \
  /path/to/original-source-or-extracted-draft.md \
  --markdown /path/to/final-quiz.md \
  --html /path/to/preview.html
```

If the script reports potentially missing lines, patch the final quiz Markdown, rerun cloze padding if needed, rerender XML/HTML, and rerun the fidelity check. Repeat until the check is clean and a manual spot check does not reveal dropped information.
