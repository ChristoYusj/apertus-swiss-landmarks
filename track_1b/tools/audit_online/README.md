# Grading-audit tools (Task G)

Team-only tools for the human grading audit and the AI cross-check (`docs/annotation_guidelines.md`, Task G).
Run them from `track_1b` with the project venv; the PDF tools need `reportlab` (build) or `pypdf` (read). The
`.html` files are sources for private claude.ai artifacts (labels saved per click in the artifact database, or
downloaded as JSON when the viewer cannot write).

## Used for the published labels (protocol audit-v4)
One annotator (A1, the team lead) graded all three blind parts; no second human.

1. `build_audit_v4.py`: splits the 522 sample items still in the dataset (seed 20261018) into a 30-item overlap
   and three parts of 164; writes `assignment.json` and `items_A1.json` ... `items_A3.json` (no grade of any kind).
2. `build_check_pdf.py <items_AN.json> <out.pdf> --blind`: one fillable PDF per part (194 answers, one per page,
   English gloss for non-French answers, no grade shown).
3. The returned PDFs' fields were exported to `audit_labels_<ID>.json` (format `audit-v4-labels`; label time =
   the PDF's save time).
4. `merge_audit_v4.py --one-annotator A1 <assignment.json> <results> <label files>`: writes `human_audit.jsonl`
   (one row per item, all under A1) and `human_audit_repeat.jsonl` (the second and third labels of the 30 shared
   items; the overlap was known, so not a blind test-retest).

`import_ai_crosscheck.py`: writes the second AI's (Hermes) grades of the audit sample as
`ai_crosscheck_audit.jsonl`, scored as an AI cross-check, not a human audit.

## Built but not the source of any published label
- `build_audit_v4_page.py` + `audit_v4.html`: online version of the same blind v4 items (collection `audit4`); all
  labels came from the PDFs.
- `read_audit_pdf.py`: reads the filled v4 PDFs straight into `human_audit.jsonl` as three separate annotators.
  The published file comes from `merge_audit_v4.py --one-annotator A1` instead (one person graded all parts).
- Non-blind check of the AI cross-check grades (the AI's proposed grade is shown): `build_check.py` (150 items),
  `human_check.html` (collection `hcheck`), `build_check_pdf.py` without `--blind`, `read_check_pdf.py`. Prepared,
  not used for any result.

## Earlier protocol v3 (replaced before any label was collected)
- `build_page.py` + `audit.html`: online page for one annotator with 40 hidden repeats (ids `<item_id>~r`),
  collection `audit`, same items and order as `landmarks-eval audit-page`. Its downloads (`audit-v1`) are read
  by `landmarks-eval merge-audit`.

      python tools/audit_online/build_page.py --dataset work/dataset --results work/dataset/responses/apertus-v1.5-70b --out <dir>
