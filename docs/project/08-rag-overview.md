# Tổng quan RAG

## Nguyên tắc

Hệ thống chỉ trả lời trong phạm vi người dùng ở [phạm vi sản phẩm](01-product-scope-and-corpus.md), từ văn bản đã được người quản trị duyệt và công bố. Không coi retrieval thành công, điểm số cao hay một trạng thái cấp văn bản là bằng chứng đủ về tính đúng pháp lý.

## Luồng runtime

Câu hỏi
-> chuẩn hóa, xác định ý định/phạm vi/thời điểm
-> hỏi lại hoặc từ chối nếu ngoài phạm vi hay thiếu dữ kiện trọng yếu
-> lọc nguồn đã duyệt, đang công bố, active và phù hợp thời điểm
-> exact lookup + PostgreSQL full-text search + vector search
-> deterministic legal ranking và evidence policy
-> tạo câu trả lời từ evidence đã chọn
-> kiểm chứng nội dung/citation
-> trả câu trả lời có citation hoặc thông báo thiếu căn cứ, kèm disclaimer

Bộ lọc eligibility phải được áp dụng trước vector search, không chỉ lọc kết quả sau khi tìm kiếm. Không có fallback sang bảng/chunk legacy. Khi người dùng nêu rõ số hiệu, có thể giới hạn tra cứu vào văn bản đó; không tự suy số hiệu từ chủ đề rồi loại các nguồn sửa đổi liên quan.

## Chiến lược truy xuất

1. Dùng exact lookup cho số hiệu, metadata và locator pháp lý rõ ràng.
2. Kết hợp full-text search và vector search để xử lý câu chữ tự nhiên; giữ tập ứng viên từ nhiều văn bản liên quan.
3. Xếp hạng cục bộ theo độ phủ thuật ngữ, locator, tiêu đề và metadata pháp lý; không để một tín hiệu chủ đề đơn lẻ quyết định nguồn.
4. Gom evidence theo tài liệu và Điều/Khoản, giữ điều kiện, ngoại lệ, ngữ cảnh cha và mốc hiệu lực.
5. Chỉ đưa evidence có trạng thái trả lời được vào generation. Near-tie hoặc evidence mâu thuẫn cần hỏi rõ hoặc abstain.

Chi tiết eligibility, truy vấn lai, ranking, temporal filtering và citation verifier nằm trong [đặc tả retrieval và citation](10-rag-retrieval-ranking-spec.md). Cấu trúc đơn vị truy xuất ở [đặc tả chunking](09-rag-chunking-spec.md); prompt và guardrail ở [đặc tả guardrail](11-rag-guardrail-spec.md).

## Giới hạn và kiểm soát

- Nếu câu trả lời phụ thuộc vào hình, bảng hoặc phụ lục chưa được xử lý, không suy diễn từ văn bản lân cận.
- Citation phải trỏ đến đúng văn bản và locator; khi kiểm chứng thất bại, chặn toàn bộ kết luận không được hỗ trợ.
- Câu hỏi về mức phạt cần đủ phương tiện, chủ thể, hành vi và thời điểm; hỏi lại nếu thiếu.
- Hỏi về thời điểm quá khứ phải dùng nội dung có hiệu lực tại thời điểm đó và tách khỏi căn cứ hiện hành.
- Disclaimer luôn được thêm cho đầu ra pháp lý.
- Chất lượng được đo bằng regression và golden evaluation độc lập; xem [chiến lược kiểm thử](07-testing-strategy.md).

RAG không tự làm corpus đầy đủ. Mỗi nhóm câu hỏi chỉ được bật sau khi nguồn, độ bao phủ cấu trúc, hiệu lực, nhãn citation và ca từ chối đã được rà soát.
