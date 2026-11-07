# Phạm vi sản phẩm và corpus

**Cập nhật:** 07/11/2026
**Trạng thái corpus:** Chưa được xác nhận đầy đủ hoặc thẩm định pháp lý.

## Đối tượng và phạm vi

Trợ lý hỏi đáp bằng tiếng Việt về quy định giao thông đường bộ tại Việt Nam, dành cho:

- Người đi bộ.
- Người đi xe đạp và xe đạp điện.
- Người đi xe máy.
- Người lái và chủ ô tô cá nhân.

Chỉ trả lời các chủ đề giao thông có văn bản nguồn phù hợp và đã được duyệt. Không mở rộng mặc định sang tư vấn cho SME, doanh nghiệp vận tải, đội xe hoặc nghiệp vụ kinh doanh vận tải. Khi thiếu phương tiện, chủ thể, địa bàn hay thời điểm cần thiết, hỏi lại hoặc nêu rõ chưa đủ căn cứ.

Giao diện hỏi đáp chỉ dùng văn bản. Không nhận diện biển báo, vạch đường hay tình huống từ ảnh; không dùng OCR. Nội dung pháp lý phụ thuộc vào hình, sơ đồ, bảng hoặc phụ lục chỉ được dùng khi phần văn bản đã được người rà soát đối chiếu với nguồn và gắn đúng vị trí. Nếu không, phải loại khỏi căn cứ trả lời.

Mọi câu trả lời pháp lý cần trích dẫn Điều/Khoản/Điểm phù hợp hoặc nói rõ chưa đủ bằng chứng, và kèm tuyên bố miễn trừ bắt buộc.

## Corpus

Các nhóm nguồn được hướng tới gồm quy tắc và điều kiện tham gia giao thông; quyền, nghĩa vụ của người đi đường và chủ xe cá nhân; xử lý vi phạm; giấy phép lái xe; đăng ký và kiểm định xe; tốc độ và khoảng cách an toàn; cùng các quy định khác gắn trực tiếp với nhóm người dùng trên.

Tài liệu bàn giao ngày 07/11/2026 ghi nhận một snapshot gồm 21 tệp DOCX. Đây chỉ là số liệu kiểm kê tại thời điểm đó, không phải manifest hiện hành hay bằng chứng rằng từng tệp là bản chính xác, đủ phụ lục, còn hiệu lực hoặc bao phủ đầy đủ câu hỏi. Cần kiểm kê lại thư mục corpus trước mỗi đợt nhập liệu và đối chiếu từng nguồn với cơ quan ban hành/cơ sở dữ liệu pháp luật chính thức.

Với mỗi nguồn, lưu tệp gốc không chỉnh sửa, URL, thời điểm tải, checksum, số hiệu, ngày hiệu lực và quan hệ sửa đổi/thay thế. Không coi một cờ hiệu lực cấp văn bản là đủ khi chỉ một số điều khoản bị sửa đổi; căn cứ phải được xác định theo nội dung và thời điểm áp dụng.

## Điều kiện đưa vào trả lời

1. Tách và giữ cấu trúc Chương/Điều/Khoản/Điểm, bảng, biểu mẫu và phụ lục cùng vị trí nguồn.
2. Gắn trạng thái cho từng phần: đã trích xuất và kiểm tra, chỉ dùng đối chiếu, ngoài phạm vi, hoặc cần rà soát. Không âm thầm bỏ phần có thể làm thay đổi nghĩa.
3. Đánh dấu nội dung phụ thuộc hình ảnh chưa được xử lý là không thể trả lời; không để mô hình tự suy diễn từ phần chữ lân cận.
4. Nhập và đánh giá ở trạng thái nháp; chỉ người quản trị mới được duyệt/công bố nội dung dùng cho tra cứu và trả lời.
5. Thử lại cùng nguồn phải idempotent, giữ provenance và không tạo bản đang hoạt động trùng lặp.
6. Trước khi bật một nhóm câu hỏi, kiểm tra độ bao phủ, hiệu lực, phạm vi, trích dẫn, trường hợp mơ hồ/thiếu căn cứ và các tình huống rủi ro cao.

Tự động hóa parser không chứng minh đã bao phủ toàn bộ gói DOCX hoặc đúng cách hiểu pháp luật. Việc công bố cần người rà soát xác nhận các ngoại lệ và nội dung có rủi ro.
