"""Utility script to seed the database with mock documents and chunks for demo day (PRD F01-F05)."""

import asyncio
import logging
from datetime import date

from sqlalchemy import select

from src.db.session import async_session_factory
from src.models.document_chunk import DocumentChunk
from src.models.legal_document import LegalDocument
from src.rag.embedding import embed_texts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_seed")

# UUIDs aligned with eval/run_eval.py and DOC_MENTION_KEYWORDS
DOCS_DATA = [
    {
        "doc_id": "10010010-0100-1001-0010-010010010019",
        "title": "Nghị định 100/2019/NĐ-CP xử phạt vi phạm giao thông đường bộ",
        "doc_type": "NGHI_DINH",
        "status": "repealed",
        "legal_status": "repealed",
        "effective_date": date(2020, 1, 1),
        "expiry_date": date(2026, 3, 1),
        "valid_from": date(2020, 1, 1),
        "valid_to": date(2026, 3, 1),
        "replaced_by_id": "33633633-3363-3363-3363-336336336336",
        "issuer": "Chính phủ",
        "source_url": "https://vbpl.vn/bo-tu-phap/pages/vbpq-toanvan.aspx?ItemID=139686",
        "domain_tags": ["xe_may", "o_to", "xu_phat"],
        "chunks": [
            {
                "chunk_type": "dieu",
                "article_num": 6,
                "clause_num": 4,
                "point_num": "g",
                "text_content": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe mô tô, xe gắn máy (kể cả xe máy điện) thực hiện hành vi vượt đèn tín hiệu đỏ (không chấp hành hiệu lệnh của đèn tín hiệu giao thông). Ngoài ra bị tước quyền sử dụng Giấy phép lái xe từ 01 đến 03 tháng.",
            },
            {
                "chunk_type": "dieu",
                "article_num": 6,
                "clause_num": 6,
                "point_num": None,
                "text_content": "Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng đối với người điều khiển xe mô tô, xe gắn máy trên đường mà trong máu hoặc hơi thở có nồng độ cồn nhưng chưa vượt quá 50 miligam/100 mililít máu hoặc chưa vượt quá 0.25 miligam/1 lít khí thở.",
            },
            {
                "chunk_type": "dieu",
                "article_num": 6,
                "clause_num": 8,
                "point_num": None,
                "text_content": "Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe mô tô, xe gắn máy trên đường mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 80 miligam/100 mililít máu hoặc vượt quá 0.4 miligam/1 lít khí thở.",
            },
        ],
    },
    {
        "doc_id": "33633633-3363-3363-3363-336336336336",
        "title": "Nghị định 336/2025/NĐ-CP thay thế một số điều của quy định cũ",
        "doc_type": "NGHI_DINH",
        "status": "active",
        "legal_status": "active",
        "effective_date": date(2026, 3, 1),
        "valid_from": date(2026, 3, 1),
        "issuer": "Chính phủ",
        "source_url": "https://vbpl.vn/...",
        "domain_tags": ["xe_may", "o_to", "xu_phat"],
        "chunks": [
            {
                "chunk_type": "dieu",
                "article_num": 9,
                "clause_num": 1,
                "point_num": None,
                "text_content": "Phạt tiền từ 400.000 đồng đến 600.000 đồng đối với người điều khiển xe mô tô, xe gắn máy thực hiện hành vi vượt đèn tín hiệu đỏ theo quy định mới nhằm hỗ trợ phân luồng giao thông.",
            }
        ],
    },
    {
        "doc_id": "10101010-1010-1010-1010-101010101020",
        "title": "Nghị định 10/2020/NĐ-CP về điều kiện kinh doanh vận tải bằng xe ô tô",
        "doc_type": "NGHI_DINH",
        "status": "active",
        "effective_date": date(2020, 4, 1),
        "issuer": "Chính phủ",
        "source_url": "https://vbpl.vn/...",
        "domain_tags": ["xe_tai", "xe_khach", "giay_phep"],
        "chunks": [
            {
                "chunk_type": "dieu",
                "article_num": 12,
                "clause_num": 2,
                "point_num": None,
                "text_content": "Xe ô tô kinh doanh vận tải hành khách từ 09 chỗ trở lên và xe kinh doanh vận tải hàng hóa bằng công-ten-nơ, xe đầu kéo phải lắp camera đảm bảo ghi, lưu trữ hình ảnh của người lái xe trong quá trình tham gia giao thông.",
            }
        ],
    },
    {
        "doc_id": "36363636-3636-3636-3636-363636363636",
        "title": "Luật Trật tự, an toàn giao thông đường bộ số 36/2024/QH15",
        "doc_type": "LUAT",
        "status": "active",
        "effective_date": date(2025, 1, 1),
        "issuer": "Quốc hội",
        "source_url": "https://vbpl.vn/...",
        "domain_tags": ["trat_tu", "an_toan"],
        "chunks": [
            {
                "chunk_type": "dieu",
                "article_num": 10,
                "clause_num": 1,
                "point_num": None,
                "text_content": "Người lái xe tham gia giao thông phải có sức khỏe phù hợp với loại xe điều khiển, có giấy phép lái xe do cơ quan nhà nước có thẩm quyền cấp phù hợp với loại xe được phép điều khiển.",
            }
        ],
    },
]
SEED_DOC_IDS = frozenset(document["doc_id"] for document in DOCS_DATA)


async def seed():
    async with async_session_factory() as session:
        # Check if already seeded
        res = await session.execute(select(LegalDocument))
        existing_docs = res.scalars().all()
        if existing_docs:
            logger.info("Database already seeded with documents. Skipping seeding.")
            return

        logger.info("Starting database seeding...")
        for doc_info in DOCS_DATA:
            doc = LegalDocument(
                doc_id=doc_info["doc_id"],
                title=doc_info["title"],
                doc_type=doc_info["doc_type"],
                status=doc_info["status"],
                legal_status=doc_info.get("legal_status", "active"),
                effective_date=doc_info["effective_date"],
                expiry_date=doc_info.get("expiry_date"),
                valid_from=doc_info.get("valid_from", doc_info["effective_date"]),
                valid_to=doc_info.get("valid_to"),
                replaced_by_id=doc_info.get("replaced_by_id"),
                issuer=doc_info["issuer"],
                source_url=doc_info["source_url"],
                domain_tags=doc_info["domain_tags"],
            )
            session.add(doc)
            logger.info(f"Created document: {doc.title}")

            # Generate embeddings for the chunks
            chunk_texts = [c["text_content"] for c in doc_info["chunks"]]
            embeddings = await embed_texts(chunk_texts)

            for chunk_data, embedding in zip(doc_info["chunks"], embeddings):
                chunk = DocumentChunk(
                    doc_id=doc_info["doc_id"],
                    text_content=chunk_data["text_content"],
                    chunk_type=chunk_data["chunk_type"],
                    article_num=chunk_data["article_num"],
                    clause_num=chunk_data["clause_num"],
                    point_num=chunk_data["point_num"],
                    status=doc_info["status"],
                    effective_date=doc_info["effective_date"],
                    embedding_vector=embedding,
                    metadata_json={},
                )
                session.add(chunk)
                logger.info(f"  Created chunk for Article {chunk.article_num}")

        await session.commit()
        logger.info("Database seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
