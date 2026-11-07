# Quy trình cập nhật kho văn bản

## Bề mặt quản trị

- Duyệt văn bản: nhận DOCX, kiểm tra parse, metadata, quan hệ và các phần rủi ro trước khi publish.
- Kho văn bản: quản lý văn bản đã hoặc từng công bố, thông tin, quan hệ, trạng thái, tóm tắt và file nguồn.
- Tra cứu văn bản: public chỉ hiển thị nội dung được phép công khai; chatbot chỉ dùng retrieval units đủ điều kiện.

API quản trị nằm dưới /api/v1/admin/legal-kb. Route cũ admin_kb.py không được mount vào runtime.

## Upload và xử lý

1. Admin tải DOCX, khai báo số hiệu, tiêu đề, loại, cơ quan, ngày ban hành/hiệu lực, nguồn và quan hệ cần thiết.
2. Backend tính SHA-256 và từ chối upload trùng nguồn đã có.
3. File nguồn được lưu ở local storage hoặc object storage; URI, checksum, nguồn và metadata được ghi vào database.
4. Parser tạo revision nháp, canonical nodes, cảnh báo, đề xuất metadata/tóm tắt và retrieval units ban đầu.
5. Admin kiểm tra lỗi parse, cấu trúc Điều/Khoản/Điểm, bảng/phụ lục, phần phụ thuộc hình, quan hệ sửa đổi và phạm vi trả lời.

Luồng hiện nhận DOCX. Không đổi đuôi PDF thành DOCX hoặc coi parse thành công là đã xác nhận độ bao phủ.

## Review và publish

Nội dung chưa được duyệt không xuất hiện trên public và không tham gia chat. Admin xử lý từng nhóm đề xuất:

- Xác nhận metadata và quan hệ giữa văn bản.
- Duyệt hoặc từ chối node; các node rủi ro cần quyết định answerable hay chỉ dùng đối chiếu.
- Kiểm tra tóm tắt chuẩn với bản nguồn.
- Xử lý cảnh báo/cấu trúc sai trước khi công bố.

Publish chỉ thành công khi revision được duyệt, có nguồn và metadata cần thiết, cấu trúc citation hợp lệ, quan hệ bắt buộc được xử lý và không còn blocker. Quyết định được ghi vào bảng audit. Không sửa trực tiếp nội dung đang công bố; thay file tạo revision mới.

Tạm ngừng một revision loại nó khỏi public/chat mà không xóa provenance. Khôi phục chỉ được thực hiện theo thao tác quản trị phù hợp; trạng thái pháp lý và trạng thái sử dụng nội bộ là hai khái niệm riêng.

## Sau khi công bố

Public documents chỉ đọc revision published phù hợp trạng thái và quyền hiển thị. Chat áp dụng thêm active filter, thời điểm hiệu lực và answerable status trước retrieval. Historical citation có thể mở nguồn lịch sử nhưng không làm nguồn đó trở thành căn cứ hiện hành.

Tải file nguồn public phải kèm cảnh báo đối chiếu với nguồn chính thức; không để lộ đường dẫn file nội bộ. Luồng chi tiết API tại [đặc tả API](03-api-spec.md); trạng thái/schema tại [database schema](05-database-schema.md).

## Lưu trữ và vận hành

- File local mặc định nằm dưới app/backend/storage/legal_kb và không thuộc Git.
- Môi trường tạm không bảo đảm file sống qua restart; production cần object storage bền vững.
- Sao lưu database và file nguồn theo cùng một mốc; kiểm tra URI/checksum sau restore.
- Migration 0016_legal_kb_names đổi tên bảng và đường dẫn local hiện hành; các revision ID lịch sử giữ nguyên để tương thích Alembic.
- Script rebuild cấu trúc/citation mặc định dry-run; chỉ chạy thao tác ghi sau backup và review báo cáo.

Mọi cập nhật corpus vẫn phải qua review/publish; không chỉnh trạng thái database hoặc bỏ bước duyệt để xử lý một câu hỏi riêng lẻ.
