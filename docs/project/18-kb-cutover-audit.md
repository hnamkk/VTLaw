# Kiểm Toán Chuyển Đổi Kho Văn Bản

## 1. Trạng thái tài liệu

Đây là tài liệu lịch sử ghi nhận giai đoạn chuyển đổi kho văn bản trước khi hoàn tất R1-R5. Tài liệu này không còn là mô tả trạng thái runtime hiện hành.

Nguồn mô tả vận hành hiện nay:

- [04-api-spec.md](04-api-spec.md)
- [05-architecture.md](05-architecture.md)
- [07-deployment-devops.md](07-deployment-devops.md)
- [08-testing-strategy.md](08-testing-strategy.md)
- [09-rag-overview.md](09-rag-overview.md)
- [16-kb-update-workflow.md](16-kb-update-workflow.md)
- [../../e2e-ui-audit-report.md](../../e2e-ui-audit-report.md)

## 2. Kết luận lịch sử đã được chốt

- Runtime public/chat đã chuyển sang kho văn bản đang công bố.
- Route admin tương thích `/api/v1/admin/kb-v2` vẫn được giữ ở mức contract nội bộ.
- Dữ liệu legacy không còn là nguồn runtime cho public/chat.
- Tên `kb_v2_*` còn lại chỉ là chi tiết schema nội bộ.

## 3. Lưu ý khi đọc tài liệu cũ

- Không dùng tài liệu này để suy ra biến môi trường, route bật/tắt hay mô hình chuyển tiếp đã kết thúc.
- Không coi các ghi chú cutover cũ là cấu hình đang dùng.
- Mọi xác nhận mới về audit UI/E2E phải đọc trong `e2e-ui-audit-report.md`.
