"""Hierarchical chunker: parsed blocks -> ChunkDraft list (spec 10 §4–§7).

Walks parser output line by line, tracking the current Chương/Điều/Khoản
context. Khoản is the primary retrieval chunk; an Điều with intro text but no
clauses yields a ``dieu`` chunk. Short chunks merge into their parent; long
chunks split on points/lines while keeping the heading path. Each emitted chunk
carries a full legal display_path and an enriched ``embedding_content``.
"""

from __future__ import annotations

import re

from src.core.config import settings
from src.rag.chunking.base import (
    CHUNK_TYPE_CHUONG,
    CHUNK_TYPE_DIEM,
    CHUNK_TYPE_DIEU,
    CHUNK_TYPE_KHOAN,
    CHUNK_TYPE_PHU_LUC,
    ChunkDraft,
    DocMeta,
)
from src.rag.chunking.structure import MarkerKind, classify_line
from src.rag.parsing.base import BlockKind, ParseResult

# Tails this chunker appends to display_path in ``_display_path``. The leaf
# pieces are: "Khoản <n>", "Điểm <letter>", "Bảng". Anchoring at end of string
# means a chapter title such as "Khoản phí và lệ phí" sitting in the middle of
# the path is left untouched.
_PATH_TAIL_RE = re.compile(r"\s*→\s*(Khoản\s+\d+|Điểm\s+\S+|Bảng)\s*$")


def _split_lines(blocks_text: str) -> list[str]:
    return [ln for ln in blocks_text.splitlines() if ln.strip()]


def build_embedding_content(meta: DocMeta, heading_path: list[str], body: str) -> str:
    """Format the context-enriched string fed to the embedding model (spec 10 §5).

    Header line carries document identity + validity; following lines carry the
    heading path so a bare Khoản keeps its Chương/Điều context when embedded.
    """
    header = " | ".join(
        part
        for part in (
            meta.document_number,
            meta.title,
            meta.doc_type,
            meta.corpus,
            meta.effective_date,
            meta.status,
        )
        if part
    )
    parts = [header, *heading_path, body]
    content = "\n".join(p for p in parts if p)
    return content[: settings.EMBEDDING_CONTENT_MAX_LEN]


class _Chunker:
    """Stateful walk over parser blocks producing raw ChunkDrafts.

    Length normalization (merge short / split long) runs as a separate pass in
    ``chunk_document`` so the structural walk stays readable.
    """

    def __init__(self, meta: DocMeta) -> None:
        self.meta = meta
        self.drafts: list[ChunkDraft] = []
        self.chapter_num: int | None = None
        self.chapter_title: str = ""
        self.article_num: int | None = None
        self.article_title: str = ""
        # Open buffer for the chunk currently being accumulated.
        self._buf: list[str] = []
        self._open: ChunkDraft | None = None

    def _heading_path(self) -> list[str]:
        path: list[str] = []
        if self.chapter_num is not None:
            label = f"Chương {self.chapter_num}"
            path.append(f"{label}: {self.chapter_title}" if self.chapter_title else label)
        if self.article_num is not None:
            label = f"Điều {self.article_num}"
            path.append(f"{label}: {self.article_title}" if self.article_title else label)
        return path

    def _display_path(self, tail: str) -> str:
        parts = [self.meta.title, *self._heading_path()]
        if tail:
            parts.append(tail)
        return " → ".join(parts)

    def _flush(self) -> None:
        """Finalize the open chunk, attaching accumulated body lines."""
        if self._open is None:
            return
        body = "\n".join(self._buf).strip()
        # Drop a bare Điều/Chương heading that gathered no intro text — child
        # chunks already carry the parent context, so an empty parent chunk is
        # noise (spec 10 §4: Chương chunk only "khi có phần mô tả riêng").
        if not body and self._open.chunk_type in (CHUNK_TYPE_DIEU, CHUNK_TYPE_CHUONG):
            self._open, self._buf = None, []
            return
        self._open.text_content = body or self._open.text_content
        self.drafts.append(self._open)
        self._open, self._buf = None, []

    def _start(self, draft: ChunkDraft, first_body: str = "") -> None:
        self._flush()
        self._open = draft
        self._buf = [first_body] if first_body else []

    def _append_unscoped_line(self, line: str, page: int | None) -> None:
        """Keep numbered preamble/annotation lines outside an Article verbatim."""
        if self._open is None:
            self._start(
                ChunkDraft(
                    text_content="",
                    chunk_type=CHUNK_TYPE_PHU_LUC,
                    display_path=f"{self.meta.title} → Thông tin ban hành",
                    source_page=page,
                    content_kind="preamble",
                ),
                first_body=line,
            )
            return
        self._buf.append(line)

    def feed_line(self, line: str, page: int | None) -> None:
        m = classify_line(line)

        if m.kind is MarkerKind.chuong:
            self._flush()
            self.chapter_num, self.chapter_title = m.number, m.title
            self.article_num, self.article_title = None, ""
            # Open a chuong chunk; if no own description follows before the first
            # Điều, _flush drops it (spec 10 §4). chapter_num is set first so the
            # heading_path reflects this chapter.
            self._start(
                ChunkDraft(
                    text_content="",
                    chunk_type=CHUNK_TYPE_CHUONG,
                    chapter_num=self.chapter_num,
                    heading_path=self._heading_path(),
                    display_path=self._display_path(""),
                    source_page=page,
                )
            )
            return

        if m.kind is MarkerKind.dieu:
            self._flush()
            self.article_num, self.article_title = m.number, m.title
            self._start(
                ChunkDraft(
                    text_content="",
                    chunk_type=CHUNK_TYPE_DIEU,
                    article_num=self.article_num,
                    chapter_num=self.chapter_num,
                    heading_path=self._heading_path(),
                    display_path=self._display_path(""),
                    source_page=page,
                )
            )
            return

        if m.kind is MarkerKind.khoan:
            # Consolidated texts commonly number amendment notes before the
            # first Article. They are source annotations, not legal clauses.
            if self.article_num is None:
                self._append_unscoped_line(line, page)
                return
            tail = f"Khoản {m.number}"
            self._start(
                ChunkDraft(
                    text_content="",
                    chunk_type=CHUNK_TYPE_KHOAN,
                    article_num=self.article_num,
                    clause_num=m.number,
                    chapter_num=self.chapter_num,
                    heading_path=self._heading_path(),
                    display_path=self._display_path(tail),
                    source_page=page,
                ),
                first_body=m.title,
            )
            return

        if m.kind is MarkerKind.diem:
            # Points stay inside their Khoản; the length pass splits along point
            # boundaries if the clause is over-length. A clause that spans
            # multiple points has no single point_num — clear it so the chunk's
            # metadata never claims to be just one point (citation integrity).
            if self._open is not None and self._open.chunk_type == CHUNK_TYPE_KHOAN:
                self._open.point_num = None
                self._buf.append(f"{m.point}) {m.title}")
                return
            # A point outside a clause is annotation/article text. Preserve it
            # without inventing a legal locator that the source does not have.
            self._append_unscoped_line(line, page)
            return

        # body continuation
        if self._open is None:
            self._start(
                ChunkDraft(
                    text_content="",
                    chunk_type=CHUNK_TYPE_PHU_LUC,
                    display_path=f"{self.meta.title} → Thông tin ban hành",
                    source_page=page,
                    content_kind="preamble",
                ),
                first_body=m.title,
            )
            return
        self._buf.append(m.title)

    def feed_table(self, text: str, page: int | None) -> None:
        self._flush()
        self.drafts.append(
            ChunkDraft(
                text_content=text,
                chunk_type=CHUNK_TYPE_PHU_LUC,
                article_num=self.article_num,
                chapter_num=self.chapter_num,
                heading_path=self._heading_path(),
                display_path=self._display_path("Bảng"),
                source_page=page,
                content_kind="table",
            )
        )

    def finish(self) -> list[ChunkDraft]:
        self._flush()
        return self.drafts


def _merge_short(drafts: list[ChunkDraft]) -> list[ChunkDraft]:
    """Keep short provisions separate so their legal locator remains exact."""
    return drafts


def _hard_wrap(lines: list[str]) -> list[str]:
    """Break any single line longer than CHUNK_MAX_LEN on word boundaries.

    A Vietnamese clause is often one long unbroken line, so line-boundary
    splitting alone can't enforce the max length; this guarantees every piece
    fed to the splitter is itself within the cap.
    """
    out: list[str] = []
    for line in lines:
        if len(line) <= settings.CHUNK_MAX_LEN:
            out.append(line)
            continue
        words = line.split(" ")
        cur = ""
        for w in words:
            if cur and len(cur) + len(w) + 1 > settings.CHUNK_MAX_LEN:
                out.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}" if cur else w
        if cur:
            out.append(cur)
    return out


def _split_on_lines(draft: ChunkDraft) -> list[ChunkDraft]:
    """Split an over-length chunk on line boundaries, preserving all coordinates."""
    parts: list[str] = []
    cur = ""
    for line in _hard_wrap(draft.text_content.splitlines()):
        if cur and len(cur) + len(line) + 1 > settings.CHUNK_MAX_LEN:
            parts.append(cur.strip())
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur.strip():
        parts.append(cur.strip())

    result: list[ChunkDraft] = []
    for text in parts:
        result.append(
            ChunkDraft(
                text_content=text,
                chunk_type=draft.chunk_type,
                chapter_num=draft.chapter_num,
                article_num=draft.article_num,
                clause_num=draft.clause_num,
                point_num=draft.point_num,
                display_path=draft.display_path,
                heading_path=draft.heading_path,
                source_page=draft.source_page,
                source_order=draft.source_order,
                content_kind=draft.content_kind,
            )
        )
    return result


def _split_on_points(draft: ChunkDraft) -> list[ChunkDraft] | None:
    """Split a long Khoản along its Điểm boundaries (spec 10 §4).

    The clause intro (lines before the first point) stays a ``khoan`` chunk;
    each point becomes a ``diem`` chunk tagged with its own point_num and a
    display_path extended to ``→ Điểm <letter>``. Returns None when the clause
    has no point markers, so the caller falls back to a plain line split.
    """
    intro: list[str] = []
    points: list[tuple[str, list[str]]] = []  # (point_letter, lines)
    for raw in draft.text_content.splitlines():
        marker = classify_line(raw)
        if marker.kind is MarkerKind.diem:
            points.append((marker.point or "", [raw]))
        elif points:
            points[-1][1].append(raw)
        else:
            intro.append(raw)

    if not points:
        return None

    pieces: list[ChunkDraft] = []

    intro_text = "\n".join(intro).strip()
    if intro_text:
        pieces.append(
            ChunkDraft(
                text_content=intro_text,
                chunk_type=CHUNK_TYPE_KHOAN,
                chapter_num=draft.chapter_num,
                article_num=draft.article_num,
                clause_num=draft.clause_num,
                point_num=None,
                display_path=draft.display_path,
                heading_path=draft.heading_path,
                source_page=draft.source_page,
                source_order=draft.source_order,
                content_kind=draft.content_kind,
            )
        )

    for letter, lines in points:
        text = "\n".join(lines).strip()
        if not text:
            continue
        diem = ChunkDraft(
            # The clause lead-in carries shared amounts/conditions for each point.
            text_content=f"{intro_text}\n{text}" if intro_text else text,
            chunk_type=CHUNK_TYPE_DIEM,
            chapter_num=draft.chapter_num,
            article_num=draft.article_num,
            clause_num=draft.clause_num,
            point_num=letter or None,
            display_path=f"{draft.display_path} → Điểm {letter}" if letter else draft.display_path,
            heading_path=[*draft.heading_path, intro_text] if intro_text else draft.heading_path,
            source_page=draft.source_page,
            source_order=draft.source_order,
            content_kind=draft.content_kind,
        )
        # A single point may itself exceed the cap — line-split it, keeping type.
        if len(diem.text_content) > settings.CHUNK_MAX_LEN:
            pieces.extend(_split_on_lines(diem))
        else:
            pieces.append(diem)

    return pieces


def _split_long(draft: ChunkDraft) -> list[ChunkDraft]:
    """Split an over-length chunk, preserving heading path (spec 10 §6).

    A long Khoản with Điểm markers splits along point boundaries into diem
    chunks; everything else (and point-free clauses) splits on line boundaries.
    Each fragment inherits the parent's legal coordinates so it stays citable.
    """
    if len(draft.text_content) <= settings.CHUNK_MAX_LEN:
        return [draft]

    if draft.chunk_type == CHUNK_TYPE_KHOAN:
        point_parts = _split_on_points(draft)
        if point_parts is not None:
            return point_parts

    return _split_on_lines(draft)


def chunk_document(parsed: ParseResult, meta: DocMeta) -> list[ChunkDraft]:
    """Turn parser output into normalized, embedding-ready ChunkDrafts.

    Pipeline: structural walk -> merge short -> split long -> enrich
    embedding_content. Empty chunks are dropped (spec 10 §8: no empty chunk may
    be published).
    """
    if meta.parser_profile == "qcvn":
        from src.rag.chunking.technical import chunk_qcvn

        return chunk_qcvn(parsed, meta)

    chunker = _Chunker(meta)
    for block in parsed.blocks:
        if block.kind is BlockKind.table:
            chunker.feed_table(block.text, block.page)
        else:
            for line in _split_lines(block.text):
                chunker.feed_line(line, block.page)
    drafts = chunker.finish()

    drafts = _merge_short(drafts)
    expanded: list[ChunkDraft] = []
    for d in drafts:
        expanded.extend(_split_long(d))

    final: list[ChunkDraft] = []
    for source_order, d in enumerate(expanded):
        if not d.text_content.strip():
            continue
        d.source_order = source_order
        d.embedding_content = build_embedding_content(meta, d.heading_path, d.text_content)
        final.append(d)
    return final
