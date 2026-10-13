# Online grading audit (Task G, protocol v3)

The online version of the blind grading-audit page, for an annotator on another device. Built from the same
drawn sample as `landmarks-eval audit-page` (identical items, order and repeats) and published as a private
claude.ai artifact with the `db`, `user` and `downloads` capabilities.

- Labels: one database document per (annotator, item) in the collection `audit` (`a`, `item`, `label`,
  `used_translation`, `unsure`, `t`). The page shows only the chosen annotator's labels, never the judge's or
  the code grader's grade.
- A viewer who cannot write keeps labels on the device and downloads `audit_labels_<ID>.json` (format
  `audit-v1`), which `landmarks-eval merge-audit` reads like the offline page's file.
- Repeated items (protocol v3 self-consistency) appear with the id `<item_id>~r`.

    python tools/audit_online/build_page.py --dataset work/dataset --results work/dataset/responses/apertus-v1.5-70b --out <dir>
