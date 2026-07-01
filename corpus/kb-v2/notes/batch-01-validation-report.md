# Batch 01 Validation Report

Date: 2026-07-03

## Summary

Batch 01 contains 5 checklist rows and 5 DOCX files. All `local_file` paths exist under `corpus/kb-v2/raw-docx/batch-01`.
All DOCX files were checked as valid Word packages containing `word/document.xml`.

## Files

| Document number | Local file | Status |
|---|---|---|
| 35/2024/QH15 | `raw-docx/batch-01/35_2024_QH15_588811.docx` | exists |
| 36/2024/QH15 | `raw-docx/batch-01/36_2024_QH15_444251.docx` | exists |
| 45/2019/QH14 | `raw-docx/batch-01/45_2019_QH14_333670.docx` | exists |
| 71/2025/QH15 | `raw-docx/batch-01/71_2025_QH15_621341.docx` | exists |
| 118/2025/QH15 | `raw-docx/batch-01/118_2025_QH15_682798.docx` | exists |

SHA-256 values are recorded in `notes/batch-01-sha256.txt`.

## Corrections Prepared

- Prepared `corpus-checklist.cleaned.csv` because the original CSV is not valid UTF-8 and was locked by another process.
- Normalized `downloaded_at` from timestamp to `YYYY-MM-DD`.
- Set `45/2019/QH14` to `foundation` because it is outside core GTVT.
- Set `71/2025/QH15` to `reference` pending admin scope review.
- Kept `118/2025/QH15` as `amendment` and linked it to `35/2024/QH15;36/2024/QH15`.

## Review Risks

- `45/2019/QH14` and `71/2025/QH15` are outside the main GTVT corpus; publish only the portions that are clearly needed as legal background.
- `118/2025/QH15` must not publish until amendment relations and affected provisions are reviewed.
- Tables, forms, appendices, and image-derived text must be marked `answerable=true` or `answerable=false` during node review.
