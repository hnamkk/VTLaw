# Hướng Dẫn Triển Khai Và DevOps
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

| Mục | Nội dung |
|---|---|
| Backend | FastAPI |
| Frontend | Next.js |
| Database | PostgreSQL 16 + pgvector |
| Cập nhật gần nhất | 02/11/2026 |

---

## 1. Môi trường phát triển

Sao chép `.env.example` sang `.env` và cấu hình các biến môi trường bên dưới. Các công cụ lập trình AI không cài hook ghi prompt hoặc gửi lịch sử sử dụng khi Git push.

### 1.1 Backend

- Dùng virtualenv tại `.venv`.
- Chạy backend qua Uvicorn/FastAPI.
- Migration dùng Alembic.

### 1.2 Frontend

- Frontend nằm tại `app/frontend`.
- Các lệnh xác nhận cơ bản:
  - `npm run lint`
  - `npm run build`
  - `npm run e2e:ui`

### 1.3 Database

- Local dùng Docker PostgreSQL với host port `5433`.
- Backend dùng DSN async tương thích SQLAlchemy (`postgresql+asyncpg://...`).

### 1.4 Dữ liệu local và Git

- Cache embedding/accent, dữ liệu Chroma tại `data/chroma/`, file phụ SQLite và thư mục test tạm được bỏ qua trong `.gitignore`.
- Các dữ liệu này lưu trên máy local, không đưa vào Git. Giữ `.env.example`, cấu hình triển khai và lockfile trong repository.

---

## 2. Docker và local run

Checklist baseline dev:

1. PostgreSQL container chạy và healthy.
2. `alembic upgrade head` hoàn tất.
3. `GET /health` trả `status=ok`.
4. Frontend build thành công nếu cần xác nhận UI production.

---

## 3. Biến môi trường đang dùng

### 3.1 Bắt buộc

| Biến | Mục đích |
|---|---|
| `DATABASE_URL` | Kết nối PostgreSQL |
| `OPENAI_API_KEY` | Gọi model/embedding |
| `SECRET_KEY` | Ký JWT |

### 3.2 Vận hành hiện hành

| Biến | Mục đích |
|---|---|
| `KB_REQUIRE_OBJECT_STORAGE` | Nếu `true`, chặn workflow publish khi storage chưa đáp ứng |
| `KB_LOCAL_STORAGE_PATH` | Root local fallback cho source/asset |
| `OBJECT_STORAGE_ENABLED` | Bật object storage nếu môi trường có |
| `NEXT_PUBLIC_API_URL` | URL backend cho frontend |
| `E2E_ADMIN_EMAIL` | Tài khoản admin cho E2E |
| `E2E_ADMIN_PASSWORD` | Mật khẩu admin cho E2E |

Không còn dùng các cờ cutover public/chat/admin của giai đoạn chuyển đổi trong runtime hiện hành.

---

## 4. Triển khai runtime hiện hành

- `main.py` mount các router auth, chat, documents, notifications, admin documents, admin assets, admin quality, admin users và traffic signs.
- Route legacy `admin_kb.py` không được mount.
- Public documents và chatbot chỉ dùng kho văn bản đang công bố.
- Văn bản `suspended` không hiện public và không được dùng cho chatbot.

---

## 5. Storage

- Source/asset có thể nằm ở local storage hoặc object storage.
- Public source và historical citation source không được lộ path nội bộ.
- Khi tải source cho public, backend luôn kèm warning header để frontend nhắc người dùng đối chiếu nguồn chính thức.

---

## 6. Tác vụ legacy

- Script publish/reconcile cũ chỉ được phép chạy khi có `--legacy-allow`.
- Đây là hàng rào an toàn để tránh runtime vô tình dùng lại luồng `LegalDocument` hoặc `document_chunks`.

---

## 7. Kiểm tra trước khi chốt thay đổi

- `git diff --check`
- `npm run lint`
- `npm run build`
- pytest liên quan theo phạm vi thay đổi
- nếu đụng UI vận hành: `npm run e2e:ui` hoặc runner `scripts/e2e_ui_audit.py`

---

## 8. Ghi chú an toàn

- Không ghi secret thật vào tài liệu hoặc log.
- Trước mọi thao tác dọn dữ liệu hoặc file cũ phải có backup rõ ràng.
- Khi cần kiểm tra smoke admin E2E, dùng `E2E_ADMIN_EMAIL` và `E2E_ADMIN_PASSWORD`, không hardcode vào mã nguồn.
