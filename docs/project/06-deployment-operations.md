# Triển khai và vận hành

## Môi trường

Ứng dụng gồm frontend Next.js, API FastAPI/LangGraph và PostgreSQL 16 với pgvector. Cấu hình ứng dụng đặt trong `.env`; không đưa secret hoặc bản sao dữ liệu lên Git.

Biến môi trường chính:

| Biến | Mục đích |
|---|---|
| `DATABASE_URL` | Kết nối PostgreSQL |
| `OPENAI_API_KEY` | LLM và embedding |
| `JWT_SECRET_KEY` | Ký token xác thực |
| `KB_LOCAL_STORAGE_PATH` | Thư mục local cho tệp nguồn |
| `OBJECT_STORAGE_ENABLED`, `OBJECT_STORAGE_PROVIDER` | Bật lưu trữ tương thích S3 |
| `KB_REQUIRE_OBJECT_STORAGE` | Yêu cầu object storage trong môi trường triển khai |
| `NEXT_PUBLIC_API_URL` | URL API dùng bởi frontend |

## Database và file nguồn

Chạy migration Alembic trước khi khởi động API. Database chứa metadata, trạng thái duyệt/công bố, retrieval units và vector; file DOCX nguồn được lưu riêng.

Mặc định local, `KB_LOCAL_STORAGE_PATH=app/backend/storage/legal_kb`. Thư mục này không được Git theo dõi. Filesystem tạm của dịch vụ cloud không phải nơi lưu bền vững; môi trường cần giữ file qua lần restart phải cấu hình object storage tương thích S3 và kiểm tra quyền đọc/ghi.

Migration `0016_legal_kb_names` đổi tên schema và đường dẫn local từ tên kỹ thuật cũ, đồng thời giữ nguyên dữ liệu. Trước khi áp dụng trên môi trường có dữ liệu, tạo backup database và file; sau migration đối chiếu số lượng bản ghi, URI và SHA-256. Migration không sao chép/đổi tên object đã lưu trong bucket S3; các URI S3 hiện có tiếp tục trỏ đến key cũ.

Nguồn chuẩn bị nhập và file runtime là hai bản khác nhau. Giữ bản tải gốc, URL, thời điểm tải và SHA-256; không ghi đè một nguồn cũ khi tải lại. Việc có file trong kho không đồng nghĩa nội dung đã được duyệt hoặc đủ căn cứ để trả lời.

## Khởi động và kiểm tra

1. Cấu hình PostgreSQL, `.env` và `OPENAI_API_KEY`.
2. Chạy `alembic upgrade head` trong `app/backend`.
3. Khởi động API và frontend bằng lệnh phát triển của từng package.
4. Xác nhận `GET /health`, đăng nhập admin, danh sách văn bản public và một lượt chat có căn cứ.
5. Khi thay đổi retrieval hoặc corpus, chạy test liên quan và bộ đánh giá đầy đủ trước khi công bố.

```render.yaml``` là cấu hình demo backend. Cần cấu hình riêng PostgreSQL, frontend, CORS và object storage; cấu hình demo không phải bảo đảm uptime hay ngân sách production.

## Backup và khôi phục

Backup database và file nguồn theo cùng một mốc; lưu bản sao tách khỏi máy/dịch vụ đang chạy. Khi khôi phục, kiểm tra schema migration, số lượng file, URI nguồn, checksum và khả năng tải file qua API trước khi bật chat. Không xóa file cũ chỉ dựa trên việc database đã được restore.
