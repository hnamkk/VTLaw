# Đặc Tả Bảo Mật Và RBAC
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

| Mục | Nội dung |
|---|---|
| Phạm vi | Auth, JWT, RBAC, public/admin access |
| Cập nhật gần nhất | 05/07/2026 |

---

## 1. Mục tiêu

Hệ thống cho phép public tra cứu văn bản và hỏi đáp ở phạm vi được kiểm soát. Mọi thao tác quản trị kho văn bản, chất lượng AI, tài sản và người dùng phải dùng JWT có role `ADMIN`.

---

## 2. Vai trò

| Role | Quyền |
|---|---|
| `PUBLIC` | Tra cứu văn bản đang công bố, hỏi đáp public, xem nguồn/citation public |
| `USER` | Có quyền public, thêm hồ sơ cá nhân, lịch sử chat, thông báo và mục đã lưu |
| `ADMIN` | Có quyền USER, thêm quản trị kho văn bản, duyệt văn bản, chất lượng AI, tài sản và người dùng |

---

## 3. Endpoint xác thực

| Endpoint | Quyền | Ghi chú |
|---|---|---|
| `POST /api/v1/auth/register` | Public | Tạo tài khoản `USER` |
| `POST /api/v1/auth/login` | Public | Trả access token và thông tin user |
| `GET /api/v1/auth/me` | USER | Đọc hồ sơ hiện tại |
| `PATCH /api/v1/auth/me` | USER | Cập nhật email hoặc tên hiển thị |
| `POST /api/v1/auth/change-password` | USER | Đổi mật khẩu |
| `POST /api/v1/auth/logout` | USER | Kết thúc phiên phía client |

---

## 4. Dependency xác thực

| Dependency | Hành vi |
|---|---|
| `get_optional_user` | Không có token thì trả `None`; token sai/hết hạn hoặc user bị khóa thì trả `401` |
| `require_user` | Bắt buộc có user hợp lệ; nếu thiếu thì trả `Bạn cần đăng nhập để tiếp tục.` |
| `require_admin` | Bắt buộc role `ADMIN`; nếu sai quyền thì trả `Tài khoản không có quyền thực hiện thao tác này.` |

Thông báo lỗi xác thực phải là tiếng Việt dễ hiểu, để UI không lộ câu tiếng Anh thô.

---

## 5. Ma trận phân quyền

| Resource | Public | USER | ADMIN |
|---|:---:|:---:|:---:|
| `POST /api/v1/chat/stream` | Có | Có | Có |
| `GET /api/v1/documents` | Có | Có | Có |
| `GET /api/v1/documents/{document_id}/source` | Có | Có | Có |
| `GET /api/v1/traffic-signs*` | Có | Có | Có |
| `/api/v1/notifications*` | Không | Có | Có |
| `/api/v1/chat/sessions*` | Không | Có | Có |
| `/api/v1/admin/*` | Không | Không | Có |

---

## 6. Bảo vệ phiên chat

- Guest chat không lưu lịch sử server-side.
- User đăng nhập chỉ thấy phiên chat thuộc chính `user_id` trong JWT.
- `session_id` từ client không được dùng để vượt quyền truy cập phiên của user khác.

---

## 7. Quản trị người dùng

- Admin có thể tạo, sửa, khóa mềm và đặt lại mật khẩu.
- Không trả `password_hash` trong response hoặc CSV.
- Admin không thể tự khóa chính mình hoặc hạ quyền admin cuối cùng đang hoạt động.
- CSV export phải tránh formula injection và không chứa secret.

---

## 8. Secret và log

- Không commit `.env`.
- Không ghi token, password hoặc authorization header thô vào log.
- E2E đọc `E2E_ADMIN_EMAIL` và `E2E_ADMIN_PASSWORD`, không hardcode credential.
