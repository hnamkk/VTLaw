# Batch 01 Upload And Review Guide

## Upload Order

1. Upload `35/2024/QH15` as `base`.
2. Upload `36/2024/QH15` as `base`.
3. Upload `45/2019/QH14` as `foundation`.
4. Upload `71/2025/QH15` as `reference`.
5. Upload `118/2025/QH15` as `amendment` after the two base road-traffic laws exist in KB v2.

## Admin Review Checklist

- Confirm title, document number, document type, issuing authority, issued date, effective date, and role.
- Review parser warnings before approving canonical nodes.
- Mark `table`, `form`, `appendix`, and `image_caption` nodes as `answerable=true` only when their text can safely support answers.
- Mark risky nodes as `answerable=false` when the content is layout-dependent, image-dependent, or outside the chatbot scope.
- Approve standard summary only after checking it summarizes the original document, not a consolidated amended version.

## Relation Review

- For `118/2025/QH15`, create/review amendment relations to `35/2024/QH15` and `36/2024/QH15`.
- If the amendment targets specific articles/clauses, fill `source_locator` and `target_locator`.
- Do not publish `118/2025/QH15` while relation or provision-level amendment evidence is unresolved.

## Staging Flags

- `KB_V2_ENABLED=true` is enough for admin upload/review.
- Keep `KB_V2_CHAT_ENABLED=false` until this batch is published and eval is ready.
- Keep `KB_V2_PUBLIC_DOCUMENTS_ENABLED=false` until viewer/download warning is confirmed.
- Do not change production flags during this batch.
