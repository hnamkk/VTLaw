# Theo dõi vận hành và chất lượng AI

## Nguồn tín hiệu

- API logs dùng để điều tra lỗi request, database, model và upload; không ghi secret, token hoặc toàn bộ dữ liệu cá nhân không cần thiết.
- Langfuse tracing có thể bật bằng cấu hình môi trường; mặc định tắt. Không bật tracing production nếu chưa rà soát dữ liệu nhạy cảm được gửi đi.
- Golden evaluation lưu trạng thái, metric, phiên bản dataset và kết quả từng case trong PostgreSQL; runner ghi báo cáo Markdown vào eval/reports/.
- Quality dashboard đọc dữ liệu vận hành và release checks đã lưu, không thay thế kiểm thử độc lập.

## API quản trị chất lượng

Router admin/quality cung cấp:

| Endpoint | Mục đích |
|---|---|
| GET /api/v1/admin/quality/overview | Tổng quan quan sát vận hành và release check gần nhất |
| GET /api/v1/admin/quality/issues | Danh sách vấn đề cần rà soát |
| POST /api/v1/admin/quality/issues/{issue_id}/review | Ghi nhận xử lý vấn đề |
| GET /api/v1/admin/quality/release-checks | Danh sách lượt đánh giá |
| GET /api/v1/admin/quality/release-checks/{run_id} | Chi tiết metric và kết quả từng case |

Các endpoint này yêu cầu quyền admin. Trạng thái invalid không đồng nghĩa pass; overview phải phân biệt dữ liệu chưa đủ mẫu, run không hợp lệ và release gate thất bại.

## Điều cần theo dõi

- Tỷ lệ lỗi API, database và provider; timeout/cancel của chat stream.
- Latency tổng thể và retrieval/generation khi metric sẵn có.
- Citation bị verifier chặn, active-filter violation, câu trả lời thiếu disclaimer và claim rủi ro không được hỗ trợ.
- Coverage và lỗi evaluator của từng lượt golden evaluation.
- Chất lượng file ingestion: lỗi parse, node rủi ro chưa review, upload trùng và lỗi đọc source URI.
- Tình trạng backup/restore PostgreSQL và object storage.

Mỗi release check phải gắn với dataset và cấu hình có thể truy lại. Không so sánh hai lượt chạy nếu khác dataset, corpus snapshot, model hoặc điều kiện chạy mà không ghi rõ khác biệt.

## Bảo vệ dữ liệu và xử lý sự cố

Không ghi API keys, mật khẩu, JWT, nội dung đầy đủ của file nguồn hoặc dữ liệu nhận dạng người dùng vào logs/traces. Khi lỗi cần tái hiện, dùng ID request/case và dữ liệu thử đã khử nhạy cảm.

Khi có vi phạm active filter, citation sai hoặc disclaimer thiếu: dừng công bố, lưu lại run/evidence, điều tra nguồn và kiểm thử hồi quy trước khi bật lại. Không chỉnh sửa bản ghi audit để làm sạch dashboard.

Ngưỡng release gate và cách gán nhãn được duy trì tại [chiến lược kiểm thử](07-testing-strategy.md). Không lưu số liệu benchmark cũ như trạng thái hiện hành; chỉ báo cáo từ artifact có ngày chạy và cấu hình tái lập.
