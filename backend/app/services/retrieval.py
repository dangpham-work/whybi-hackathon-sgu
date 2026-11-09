"""RetrievalService – RAG trên document_chunks (pgvector, HNSW cosine) – trích dẫn trang (mục 2.2.3). Chủ: Đăng
(C1-11).

Nhúng: văn bản đã bóc theo trang (C1-09, `pages.json`) → đoạn ~500 token chồng 50 theo mục (mục 6.1.1) → embedding →
`document_chunks` kèm trang. Truy hồi: embedding câu hỏi → cosine gần nhất trong các tài liệu PARSED của lớp.
"""

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.gateway import LLMGateway, get_gateway
from app.models.enums import DocumentStatus
from app.models.users import DocumentChunk, SyllabusDocument

CHUNK_TOKENS = 500
CHUNK_OVERLAP = 50
MAX_CHUNKS = 2000  # chặn tài liệu khổng lồ làm tràn bộ nhớ / hạn mức embedding
EMBED_BATCH = 32
_CHAPTER = re.compile(r"^\s*(chương|bài|phần)\s+(\d+|[ivxlc]+)\b", re.I)


@dataclass
class Chunk:
    chapter: str | None
    section_title: str | None
    content: str
    page_from: int
    page_to: int


@dataclass
class Passage:
    content: str
    page_from: int | None
    page_to: int | None
    chapter: str | None
    section_title: str | None
    score: float  # cosine, 1 = trùng


def chunk_pages(pages: list[dict[str, Any]], size: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """Chia theo mục: tiêu đề "Chương…" mở chương, tiêu đề khác mở mục; mục dài cắt ~`size` token, chồng `overlap`.
    Tiêu đề áp dụng từ đầu trang chứa nó. ponytail: 1 từ ≈ 1 token – đổi sang tokenizer thật nếu cần chính xác."""
    sections: list[tuple[str | None, str | None, list[tuple[str, int]]]] = []
    chapter = section = None
    cur: list[tuple[str, int]] = []
    for p in pages:
        heads = p.get("headings", [])
        if heads:
            if cur:
                sections.append((chapter, section, cur))
                cur = []
            for h in heads:
                if _CHAPTER.match(h):
                    chapter, section = h.strip(), None
                else:
                    section = h.strip()
        cur += [(w, p["number"]) for w in p["text"].split()]
    if cur:
        sections.append((chapter, section, cur))

    chunks: list[Chunk] = []
    for chap, sec, words in sections:
        start = 0
        while start < len(words) and len(chunks) < MAX_CHUNKS:
            piece = words[start : start + size]
            chunks.append(Chunk(chap, sec, " ".join(w for w, _ in piece), piece[0][1], piece[-1][1]))
            if start + size >= len(words):
                break
            start += size - overlap
    return chunks


class RetrievalService:
    def __init__(self, db: Session, gateway: LLMGateway | None = None) -> None:
        self.db = db
        self.gateway = gateway

    @property
    def gw(self) -> LLMGateway:
        return self.gateway or get_gateway()

    def index_document(self, document_id: UUID, pages: list[dict[str, Any]]) -> int:
        """Chia đoạn + embedding + lưu. Chạy lại không nhân đôi (xóa đoạn cũ của tài liệu trước). Trả số đoạn."""
        chunks = chunk_pages(pages)
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH):
            vectors += self.gw.embed([c.content for c in chunks[i : i + EMBED_BATCH]])
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        self.db.add_all(
            DocumentChunk(
                document_id=document_id,
                chapter=c.chapter and c.chapter[:200],
                section_title=c.section_title and c.section_title[:300],
                content=c.content,
                embedding=v,
                page_from=c.page_from,
                page_to=c.page_to,
            )
            for c, v in zip(chunks, vectors, strict=True)
        )
        self.db.commit()
        return len(chunks)

    def has_chunks(self, class_id: UUID) -> bool:
        return (
            self.db.scalar(
                select(DocumentChunk.id)
                .join(SyllabusDocument, SyllabusDocument.id == DocumentChunk.document_id)
                .where(SyllabusDocument.class_id == class_id, SyllabusDocument.status == DocumentStatus.PARSED)
                .limit(1)
            )
            is not None
        )

    def retrieve(self, class_id: UUID, query: str, k: int = 5, document_id: UUID | None = None) -> list[Passage]:
        """k đoạn giáo trình gần `query` nhất trong các tài liệu PARSED của lớp (mới nhất ưu tiên khi hòa).
        `document_id`: chỉ lấy đoạn của một tài liệu (rubric của cây dựng từ tài liệu đó)."""
        qv = self.gw.embed([query])[0]
        dist = DocumentChunk.embedding.cosine_distance(qv)
        stmt = (
            select(DocumentChunk, dist.label("dist"))
            .join(SyllabusDocument, SyllabusDocument.id == DocumentChunk.document_id)
            .where(SyllabusDocument.class_id == class_id, SyllabusDocument.status == DocumentStatus.PARSED)
        )
        if document_id is not None:
            stmt = stmt.where(DocumentChunk.document_id == document_id)
        rows = self.db.execute(stmt.order_by(dist, SyllabusDocument.uploaded_at.desc()).limit(k)).all()
        return [
            Passage(c.content, c.page_from, c.page_to, c.chapter, c.section_title, 1 - float(d or 1.0)) for c, d in rows
        ]
