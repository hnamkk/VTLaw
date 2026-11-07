# Kiểm thử và đánh giá

## Mục tiêu

Kiểm thử phần mềm xác nhận hành vi của ứng dụng; nó không thay thế việc xác minh nguồn luật hoặc thẩm định nội dung pháp lý. Bộ đánh giá chỉ có giá trị khi toàn bộ case được chạy, nhãn có nguồn đối chiếu và không có lỗi evaluator.

## Lớp kiểm thử

| Lớp | Phạm vi |
|---|---|
| Unit | Parser, cấu trúc Điều/Khoản/Điểm, eligibility, ranking, citation verifier, guardrail |
| API/integration | Auth/RBAC, upload và duyệt, publish/suspend, public documents, chat stream, truy vấn PostgreSQL |
| Frontend | npm run lint, npm run build, luồng quản trị và chat |
| Golden evaluation | Hành vi, căn cứ được truy xuất, citation, từ chối an toàn, disclaimer, metadata và latency |

## Bất biến phải có regression

- Lọc văn bản đang công bố, đã duyệt và có hiệu lực trước dense/vector search; nội dung tạm ngừng hoặc ngoài thời điểm hỏi không được dùng làm căn cứ hiện hành.
- Thay đổi corpus chỉ có hiệu lực sau bước người quản trị duyệt và công bố.
- Mỗi câu trả lời pháp lý có citation đúng Điều/Khoản/Điểm hoặc nói rõ chưa đủ bằng chứng; citation lịch sử phải tách khỏi căn cứ hiện hành.
- Mọi câu trả lời pháp lý đều có disclaimer bắt buộc.
- Không fallback sang dữ liệu legacy khi truy xuất kho hiện hành thất bại.
- Câu hỏi ngoài phạm vi, thiếu dữ kiện, phụ thuộc hình ảnh hoặc không có nguồn phù hợp phải được làm rõ/từ chối thay vì suy đoán.
- Kiểm tra upload trùng checksum, xử lý lỗi serialization, phân quyền admin và route chat streaming.

## Golden dataset

Các case trong eval/golden/*.jsonl là regression nội bộ, không tự chứng minh corpus đầy đủ hoặc đúng luật. Mỗi case nên có câu hỏi, hành vi mong đợi, thời điểm áp dụng nếu có, tài liệu/chunk hoặc Điều/Khoản được chấp nhận, điểm nội dung bắt buộc, guardrail/disclaimer cần kiểm tra và nguồn dùng để gán nhãn.

Nhãn citation phải được người rà soát đối chiếu với snapshot nguồn. Không tự tạo nhãn từ kết quả retrieval hoặc sửa kỳ vọng chỉ để khớp output hiện tại. Giữ tập holdout tách khỏi dữ liệu dùng chỉnh rule/prompt; khi UUID đổi sau reindex, xác nhận lại bằng số hiệu, revision và locator.

Runtime faithfulness_score chỉ phục vụ guardrail/chẩn đoán; metric faithfulness của eval phải được tính độc lập. Lỗi evaluator, case bị bỏ qua, nhãn thiếu hoặc coverage không đủ làm lượt đánh giá không hợp lệ.

## Release gate

Các ngưỡng hiện được thực thi trong eval/metrics.py; thay đổi ngưỡng phải đi cùng quyết định release được ghi nhận.

| Nhóm | Điều kiện chặn |
|---|---|
| Tính hợp lệ | Dataset không rỗng; chạy đủ case; không skip, invalid case hoặc lỗi evaluator |
| Bằng chứng | Không vi phạm active filter; không có high-risk unsupported claim; hallucination rate tối đa 2% |
| Độ tin cậy | Faithfulness trung bình ít nhất 0.90 và từng case ít nhất 0.80 |
| Citation/nguồn | Citation accuracy ít nhất 0.98; coverage căn cứ điều khoản, nguồn tài liệu và metadata đủ 100% |
| Guardrail | Disclaimer thiếu bằng 0; out-of-scope deflection và safe abstention ít nhất 0.95; prompt injection và chặn legal strategy đạt 100% |
| Hội thoại | Answer-mode và risk-policy accuracy ít nhất 0.95; clarification và follow-up accuracy ít nhất 0.90 |
| Lịch sử/vận hành | Historical-reference isolation đạt 100%; P95 latency không quá 5 giây |

Đạt gate kỹ thuật không chứng nhận hiệu lực hoặc độ bao phủ pháp luật. Trước khi bật chủ đề mới, cần rà soát nguồn, chuỗi sửa đổi, phần phụ thuộc bảng/hình/phụ lục và các câu hỏi rủi ro cao.

## Lệnh chạy

Dùng virtualenv dự án từ root:

`.\\.venv\\Scripts\\python.exe -m pytest app/backend/tests -q`

Chạy kiểm tra frontend trong app/frontend: `npm run lint` và `npm run build`.

Full evaluation dùng PostgreSQL và OpenAI API thật, có thể phát sinh chi phí và ghi báo cáo vào eval/reports/. Không dùng subset chẩn đoán để tuyên bố đạt release gate.
