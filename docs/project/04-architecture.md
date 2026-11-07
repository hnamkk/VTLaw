# Kiến trúc hệ thống

## Thành phần

| Thành phần | Trách nhiệm |
|---|---|
| Next.js frontend | Chat, tra cứu văn bản và màn hình quản trị |
| FastAPI | API public/admin, xác thực, streaming và tích hợp dữ liệu |
| LangGraph agent | Điều phối guardrail, retrieval, evidence, generation và kiểm chứng |
| PostgreSQL + pgvector | Người dùng, hội thoại, metadata pháp lý, cấu trúc văn bản, retrieval units và vector |
| Object storage | Lưu file nguồn/rendition khi được cấu hình; database giữ URI và provenance |
| OpenAI | Model hội thoại và embedding theo cấu hình |

Ứng dụng là một backend FastAPI và một frontend web; không có service riêng cho từng miền. Schema và migration database được mô tả tại [database schema](05-database-schema.md).

## Luồng hỏi đáp

1. Frontend gửi câu hỏi đến POST /api/v1/chat/stream; API xác thực người dùng nếu có phiên đăng nhập.
2. Agent chuẩn hóa ngữ cảnh, kiểm tra phạm vi và yêu cầu làm rõ khi thiếu dữ kiện quan trọng.
3. Retrieval áp dụng eligibility của tài liệu đã duyệt/công bố/active trước vector search, sau đó kết hợp exact lookup, full-text và vector.
4. Evidence policy chọn căn cứ, giữ locator và thời điểm áp dụng.
5. Model chỉ được yêu cầu trả lời dựa trên evidence đã chọn; verifier kiểm tra claim/citation.
6. API stream kết quả có metadata, citation hợp lệ hoặc thông báo thiếu căn cứ, cùng disclaimer bắt buộc.

Chi tiết RAG nằm trong [tổng quan RAG](08-rag-overview.md), [retrieval và citation](10-rag-retrieval-ranking-spec.md) và [guardrail](11-rag-guardrail-spec.md).

## Luồng quản trị văn bản

Admin gửi DOCX đến /api/v1/admin/legal-kb. Backend lưu file nguồn, parse thành cấu trúc pháp lý, tạo đề xuất metadata/tóm tắt và các đơn vị cần rà soát. Admin xác nhận nội dung, quan hệ và trạng thái trước khi publish. Chỉ dữ liệu đã duyệt/công bố mới được dùng cho public/chat.

File local dùng KB_LOCAL_STORAGE_PATH; môi trường cần file bền vững phải dùng object storage. Không lưu bytes file lớn trực tiếp trong PostgreSQL. Chi tiết trạng thái và điều kiện publish tại [quy trình kho văn bản](13-kb-workflow.md).

## Quyền sở hữu và ranh giới

- Frontend không tự quyết định hiệu lực hay tính hợp lệ của citation; backend là nguồn quyết định.
- Model không tự tạo số hiệu, locator hoặc căn cứ pháp lý không có trong evidence.
- Admin workflow quản lý trạng thái và audit; chat/public chỉ đọc dữ liệu đủ điều kiện.
- Mọi lỗi retrieval, verifier hoặc database phải fail closed đối với kết luận pháp lý.
- Bản lưu local, object storage và database backup phải được khôi phục/đối chiếu cùng nhau.

Thiết kế API nằm ở [API specification](03-api-spec.md); vận hành và lưu trữ ở [deployment operations](06-deployment-operations.md).
