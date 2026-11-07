# Retrieval, ranking và citation

Runtime truy xuất hiện hành nằm ở src.rag.retrieval.hybrid_legal; điều phối tại LangGraph agent. Quy tắc dưới đây áp dụng cho chat/public, không áp dụng cho dữ liệu nháp của quy trình admin.

## Eligibility trước search

Trước dense/vector search, truy vấn phải giới hạn vào:

- Văn bản có legal_status=active.
- Revision đã review_status=approved và publication_status=published.
- Node đã được duyệt.
- Retrieval unit answerable_status=active và có hiệu lực tại query_date, nếu có khoảng thời gian hiệu lực.

Không được chạy tìm kiếm toàn bộ vector rồi mới lọc kết quả. Hỏi lịch sử dùng nhánh lịch sử riêng; kết quả lịch sử không được trộn vào citation hiện hành. Khi người dùng nêu rõ số hiệu, giới hạn theo văn bản đó và không semantic-fallback sang văn bản gần nghĩa nếu không tìm thấy.

## Candidate và ranking

1. Exact lookup xử lý số hiệu, Điều/Khoản/Điểm và metadata có cấu trúc.
2. PostgreSQL full-text search bắt từ ngữ pháp lý và từ khóa chính xác.
3. Vector search bắt paraphrase và câu hỏi tự nhiên.
4. Deterministic local ranker xếp hạng candidate theo độ khớp nội dung, locator, tiêu đề và metadata; giới hạn candidate theo văn bản để tránh một nguồn lấn át.
5. Evidence policy gom các đoạn cùng căn cứ, giữ phần mở đầu/điều kiện của khoản và xử lý near-tie, mâu thuẫn hoặc nhiều khả năng bằng hỏi lại/abstain.

Không dùng bảng chủ đề cố định để ép câu hỏi vào một văn bản/Điều. Nguồn sửa đổi và văn bản bổ trợ phải có cơ hội vào tập candidate. Query expansion được kiểm soát bởi query policy trong repository; thay đổi policy cần test regression.

## Temporal behavior

Với câu hỏi có thời điểm áp dụng, chỉ dùng phiên bản có hiệu lực tại ngày được hỏi. Khoảng hiệu lực là [effective_from, effective_to), trong đó ngày bắt đầu được tính và ngày kết thúc không được tính. Văn bản chưa có hiệu lực không được dùng thay cho văn bản đang áp dụng.

Historical citation có thể mở lại để giữ provenance cho câu trả lời cũ, nhưng không được làm thay đổi eligibility của câu hỏi mới.

## Citation contract

Mỗi khẳng định pháp lý phải có căn cứ phù hợp hoặc được thay bằng thông báo chưa đủ bằng chứng. Citation tối thiểu gắn với văn bản, retrieval unit/chunk, locator Điều/Khoản/Điểm (hoặc locator kỹ thuật khi không có cấu trúc pháp lý), source URL, đoạn trích và verification status.

Citation phải khớp đúng tài liệu và locator. Không gắn citation chỉ vì retrieval tìm được văn bản, câu hỏi nhắc số hiệu hoặc chỉ có một candidate. Nếu nhiều văn bản có cùng locator mà không phân biệt được nguồn, không tự chọn nguồn có điểm cao nhất. Mỗi lần một claim viện dẫn một chunk đều phải được kiểm tra; không bỏ qua lần sau vì chunk từng xuất hiện.

Hai dạng đầu ra cần được xác minh:

- Câu trả lời dựng trực tiếp từ server: so nội dung với evidence đã chọn; chỉ gắn citation khi khớp.
- Văn xuôi do LLM tạo: kiểm tra locator, văn bản, số liệu và nội dung claim với evidence; kiểm tra cả phủ định, chủ thể, điều kiện và ngoại lệ khi có thể.

Không bỏ qua kiểm tra vì câu bắt đầu bằng “Theo” hoặc vì model tự nêu một số Điều. Nếu có viện dẫn sai hoặc claim không được hỗ trợ, chặn toàn bộ câu trả lời do model tạo; không chỉ xóa riêng citation rồi giữ kết luận. Ngoại lệ hẹp: khi câu trả lời chỉ nói chưa tìm thấy căn cứ và không chứa claim cần kiểm chứng, backend có thể trả template tra cứu metadata.

## Trạng thái verifier

| Status | Cách dùng |
|---|---|
| verified | Locator, trạng thái và các heuristic nội dung đạt kiểm tra |
| partial | Chỉ đối chiếu được một phần; vẫn phải qua guardrail tổng |
| unverified | Chưa đủ bằng chứng để xác nhận |
| blocked | Nguồn không được phép áp dụng cho câu hỏi |

Các trạng thái là tín hiệu kỹ thuật, không phải chứng nhận ngữ nghĩa hay thẩm định pháp lý. Kiểm tra từ vựng/số liệu không chứng minh được mọi claim. Khi không còn citation hợp lệ, evidence rỗng hoặc guardrail không đạt, trả thông báo thiếu căn cứ và xóa citation không hợp lệ.

Đoạn trích không được cắt theo giới hạn ký tự nếu làm mất điều kiện áp dụng. Nhiều khoản trong cùng văn bản vẫn có citation riêng. Metadata phục vụ embedding không được hiển thị như nội dung luật.

## Regression

Bao gồm ít nhất: Điều không tồn tại; đúng Điều nhưng sai văn bản; sai số tiền; sai phương tiện/chủ thể; claim phủ định; cùng chunk được viện dẫn nhiều lần; nguồn inactive/suspended/future; nhiều candidate gần điểm; citation lịch sử; thiếu căn cứ; disclaimer.

Đánh giá độc lập phải dùng nhãn Điều/Khoản và evidence được người rà soát xác nhận. Điểm faithfulness runtime chỉ dành cho guardrail/chẩn đoán, không dùng làm metric eval. Xem [chiến lược kiểm thử và release gate](07-testing-strategy.md).
