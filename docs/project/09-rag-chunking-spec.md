# RAG parsing and chunking

## Supported input

The current legal knowledge base upload path accepts DOCX only. PDF parsing, OCR, and image understanding are not part of this workflow. Text that depends on an image, diagram, or scanned page must not be inferred from nearby text; it needs a human-verified textual source before it can support an answer.

## Parse output

The DOCX parser and legal chunker preserve source order and structure, including chapter, article, clause, point, preamble, and table content where detected. Each canonical node stores its source order, heading path, display path, source page when available, parser confidence, and structured locator metadata.

Canonical nodes are a reviewable representation of one document revision. Structural-only nodes preserve hierarchy but do not become retrieval evidence. Normal legal-text nodes can be approved during parsing; tables, forms, appendices, and other risky content require an explicit answerability decision. Administrative matter and editorial notes remain available for audit but are marked review-only.

## Retrieval unit construction

Retrieval units are created from approved, answerable canonical nodes during publication, not directly from the upload. Their text includes the legal text and enough document/heading context to distinguish similarly worded rules. Citation labels and locators are retained with each unit. The publication workflow applies the eligibility and effective-date rules described in [retrieval and ranking](10-rag-retrieval-ranking-spec.md).

Do not merge text across legal boundaries in a way that changes its locator or scope. When a provision is split for retrieval, keep its heading path and shared introductory conditions with each child unit. Empty structural nodes are retained in the tree but are not embedded.

## Corrections and reprocessing

Parser or source corrections create a new document revision. Review the new parse and its answerability decisions before publication; do not overwrite a published source or silently re-index changed text. Parser warnings and low-confidence areas must be resolved or excluded from answerable retrieval by the reviewer.

The current parser and embedding version values are stored with revision and retrieval-unit metadata so a later reparse can be audited and compared.
