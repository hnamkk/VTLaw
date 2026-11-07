# Corpus văn bản

Thư mục này lưu checklist và ghi chú nguồn phục vụ chuẩn bị nhập văn bản:

- raw-docx/: bản DOCX tải về theo batch; bị Git ignore.
- notes/: nguồn, checksum, kết quả kiểm tra và quyết định review.
- corpus-checklist.csv: checklist dạng text; bản cleaned là bản đã chuẩn hóa riêng.

Batch 01 hiện có 5 DOCX theo ghi chú kiểm tra. Đây không phải toàn bộ corpus sản phẩm và không chứng minh các văn bản đã được thẩm định hiệu lực hoặc đủ phụ lục. Tài liệu scope mô tả snapshot 21 tệp tại thời điểm bàn giao; cần kiểm kê lại trước khi đánh giá độ bao phủ.

Giữ file nguồn nguyên trạng, ghi URL, ngày tải và SHA-256. Không upload/publish chỉ vì file có trong thư mục. Chat chỉ được dùng nội dung sau khi admin review và publish trong Kho văn bản. Trải nghiệm phát hành chỉ dùng văn bản, không OCR/nhận diện hình ảnh.

File runtime nằm riêng ở app/backend/storage/legal_kb hoặc object storage. Sao lưu file và database cùng mốc; xem [hướng dẫn triển khai/vận hành](../../docs/project/06-deployment-operations.md).
