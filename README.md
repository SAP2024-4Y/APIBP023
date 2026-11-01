# Exam Eval System

Automatic evaluation of handwritten exam answer sheets.

## The problem

Teachers grading scanned answer sheets face a harder task than reading
handwriting. The same page has to be understood before it can be marked:

- Students write question numbers inconsistently, or leave them out.
- They answer questions out of order.
- A single answer may be a paragraph, a numbered list, or a diagram.
- One page can hold several subparts, and one answer can span pages.
- A handwritten `1.` might be question one, or just the first point in a list.

A plain "OCR then ask an LLM to grade" pipeline gets these wrong, because
it decides what the marks should be before it has reliably decided which
question the answer even belongs to.

This tool keeps three decisions separate and traceable:

1. **What the student wrote** — the recognised text and where it sits on the page.
2. **Which question it answers** — mapped to a canonical question tree, or flagged when unclear.
3. **How many marks it earns** — scored against a teacher-approved rubric, only after mapping.

Keeping identification apart from evaluation is what makes the result
reviewable: a teacher can see exactly what the system read, where it
mapped it, and why it gave the marks it did.

## Prototype

A small, dependency-free Python prototype lives in [exam_eval/](exam_eval/).
It runs on text input so the mapping and scoring logic stays readable,
with the OCR and vision stages left as clear boundaries. See
[Architecture.md](Architecture.md) for the full design.

```bash
python3 main.py
```

This evaluates the bundled samples in [sample_data/](sample_data/): one
clean sheet (answered out of order, with subparts and a point-wise list)
and one deliberately ambiguous sheet that gets flagged for teacher review.
