# Trợ lý Tra cứu và Tuân thủ Quy định Giao thông Vận tải

Ứng dụng hỏi đáp pháp luật giao thông đường bộ bằng tiếng Việt. Chat chỉ sử dụng căn cứ đã qua review và công bố; câu trả lời pháp lý cần citation Điều/Khoản/Điểm hoặc nêu chưa đủ bằng chứng, đồng thời luôn có disclaimer.

## Phạm vi

Đối tượng phát hành:

- Người đi bộ.
- Người đi xe đạp và xe đạp điện.
- Người đi xe máy.
- Người lái và chủ ô tô cá nhân.

Giao diện hỏi đáp dùng văn bản thuần túy; không OCR hay nhận diện biển/vạch từ ảnh. Không mở rộng mặc định sang SME, doanh nghiệp vận tải hoặc đội xe. Nội dung phụ thuộc hình, bảng hay phụ lục chỉ được dùng khi đã được kiểm tra và có vị trí nguồn rõ ràng.

## Trạng thái corpus

Tài liệu bàn giao ngày 07/11/2026 ghi nhận snapshot 21 tệp DOCX, nhưng chưa xác nhận đây là inventory hiện hành, đủ phạm vi hoặc đã thẩm định hiệu lực. File có mặt trong repository/kho lưu trữ không đồng nghĩa đã được duyệt để chatbot sử dụng. Quy tắc corpus và điều kiện bật chủ đề nằm ở [phạm vi sản phẩm](docs/project/01-product-scope-and-corpus.md).

Mọi thay đổi corpus phải đi qua upload, review và publish có người quản trị duyệt. Chat/public không được dùng dữ liệu nháp hoặc fallback sang dữ liệu legacy.

## Kiến trúc

| Tầng | Công nghệ |
|---|---|
| Frontend | Next.js, React |
| API/agent | FastAPI, LangGraph |
| Database/vector | PostgreSQL, pgvector |
| LLM/embedding | OpenAI |
| Retrieval | Exact lookup, PostgreSQL full-text, vector search và deterministic legal ranking |
| File nguồn | Local cho phát triển; object storage tương thích S3 cho môi trường cần lưu bền vững |

Luồng hỏi đáp: guardrail/phạm vi -> lọc eligibility trước vector search -> hybrid retrieval -> ranking/evidence policy -> generation -> citation verification -> disclaimer. Xem [tổng quan RAG](docs/project/08-rag-overview.md).

## API chính

| Endpoint | Mục đích |
|---|---|
| GET /health | Health check |
| POST /api/v1/chat/stream | Hỏi đáp theo SSE |
| GET /api/v1/documents | Tra cứu văn bản public |
| /api/v1/admin/legal-kb | Quản trị kho văn bản |
| /api/v1/admin/quality | Theo dõi chất lượng AI |

API chi tiết tại [đặc tả API](docs/project/03-api-spec.md).

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| app/backend/src/api/v1 | FastAPI routes |
| app/backend/src/legal_kb | Upload, parse, review, publish và retrieval data |
| app/backend/src/rag | LangGraph, prompts, guardrails, retrieval và verification |
| app/backend/src/models | SQLAlchemy models |
| app/frontend | Next.js application |
| corpus/legal-kb | Checklist và ghi chú nguồn; file DOCX lớn không commit |
| eval/golden | Bộ regression/evaluation |
| docs/project | Tài liệu chuẩn của dự án |

## Chạy local

Yêu cầu: Python virtualenv tại root là .venv, Node.js, PostgreSQL 16/pgvector và API key OpenAI.

1. Tạo .env từ .env.example và thêm OPENAI_API_KEY.
2. Chạy migration Alembic trước khi khởi động API.
3. Khởi động backend tại cổng 8000 và frontend từ app/frontend.
4. API docs có tại http://localhost:8000/docs.

PowerShell từ root:

`Copy-Item .env.example .env`
`.\\.venv\\Scripts\\python.exe -m alembic -c app/backend/alembic.ini upgrade head`
`.\\.venv\\Scripts\\python.exe -m uvicorn src.main:app --app-dir app/backend --reload --port 8000`

Frontend:

`cd app/frontend`
`npm ci`
`npm run dev`

## Kiểm tra

`.\\.venv\\Scripts\\python.exe -m pytest app/backend/tests -q`

Trong app/frontend, chạy `npm run lint` và `npm run build`. Full evaluation dùng PostgreSQL và OpenAI API thật, có thể phát sinh chi phí; cách chạy và release gate nằm trong [chiến lược kiểm thử](docs/project/07-testing-strategy.md).

## Tài liệu chuẩn

1. [Phạm vi sản phẩm và corpus](docs/project/01-product-scope-and-corpus.md)
2. [UI và workflow](docs/project/02-ui-workflows.md)
3. [API](docs/project/03-api-spec.md)
4. [Kiến trúc](docs/project/04-architecture.md)
5. [Database schema](docs/project/05-database-schema.md)
6. [Triển khai và vận hành](docs/project/06-deployment-operations.md)
7. [Kiểm thử và đánh giá](docs/project/07-testing-strategy.md)
8. [Tổng quan RAG](docs/project/08-rag-overview.md)
9. [Chunking](docs/project/09-rag-chunking-spec.md)
10. [Retrieval, ranking và citation](docs/project/10-rag-retrieval-ranking-spec.md)
11. [Prompt và guardrail](docs/project/11-rag-guardrail-spec.md)
12. [Bảo mật và RBAC](docs/project/12-security-rbac.md)
13. [Quy trình cập nhật kho văn bản](docs/project/13-kb-workflow.md)
14. [Theo dõi vận hành và chất lượng AI](docs/project/14-observability.md)
