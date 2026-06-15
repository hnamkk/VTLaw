# Đặc Tả Kho Văn Bản Hợp Nhất

## 1. Mục Tiêu

Tài liệu này là đặc tả mục tiêu cho hệ thống kho văn bản dùng trong chatbot hỏi đáp
pháp luật lĩnh vực giao thông vận tải đường bộ.

Từ nay, sản phẩm không tách thành các nhãn như "KB cũ", "KB v2", "revision",
"node" hay "workspace". Toàn bộ được thống nhất thành:

| Tên dùng trong sản phẩm | Ý nghĩa |
|---|---|
| `Kho văn bản` | Nơi admin quản lý văn bản đã công bố |
| `Kho dữ liệu` | Tên tổng quát cho dữ liệu mà chatbot được phép dùng |
| `Duyệt văn bản` | Nơi admin tải lên, kiểm tra, chỉnh sửa và công bố văn bản |
| `Tra cứu văn bản` | Nơi người dùng tìm, đọc và tải văn bản đã công bố |

Mục tiêu quan trọng nhất: chatbot chỉ được trả lời từ dữ liệu đã được admin kiểm tra
và công bố. Nếu chưa đủ căn cứ trong kho dữ liệu, chatbot phải xin lỗi và nói rõ
không tìm thấy căn cứ phù hợp.

## 2. Phạm Vi

| Hạng mục | Quyết định |
|---|---|
| Lĩnh vực | Giao thông vận tải đường bộ và các văn bản nền cần thiết |
| Phạm vi pháp luật | Không số hóa toàn bộ pháp luật Việt Nam |
| Cách đưa dữ liệu vào hệ thống | Admin tải văn bản lên |
| Định dạng ưu tiên | DOCX |
| PDF | Không dùng trong luồng công bố chính giai đoạn này |
| Nguồn mặc định | `Thư viện pháp luật` |
| Lưu file | Hiện tại có thể lưu local; đích đến là R2 hoặc nơi lưu trữ đám mây tương thích |
| Dữ liệu cũ | Xóa, không dùng làm nguồn cho kho dữ liệu mới |
| File nguồn cũ | Không giữ lại |
| Lịch sử chat/citation cũ | Không giữ lại |
| Giao diện riêng của kho mới | Bỏ hoàn toàn |

## 3. Nguyên Tắc Bắt Buộc

| Nguyên tắc | Quy tắc triển khai |
|---|---|
| Chỉ dùng dữ liệu đã công bố | Chatbot chỉ đọc văn bản có trạng thái `Đang công bố` |
| Không dùng dữ liệu tạm ngừng | Văn bản `Tạm ngừng` không xuất hiện public và không dùng để trả lời |
| Không suy đoán | Không có căn cứ thì xin lỗi và nói chưa tìm thấy |
| Có căn cứ rõ ràng | Câu trả lời pháp lý phải dẫn được điều, khoản hoặc phần văn bản liên quan |
| Có cảnh báo pháp lý | Câu trả lời pháp lý luôn có cảnh báo rằng thông tin chỉ phục vụ tham khảo |
| Admin kiểm tra trước khi công bố | Dữ liệu tải lên chưa được dùng cho chatbot cho tới khi công bố |
| Không trộn dữ liệu cũ | Không lấy lại chunk, embedding, file nguồn, metadata, summary hoặc quan hệ từ kho cũ |
| Tiếng Việt dễ hiểu | Giao diện không dùng từ kỹ thuật hoặc từ chuyên ngành nội bộ |

## 4. Ba Màn Hình Chính

### 4.1 Duyệt văn bản

`Duyệt văn bản` là nơi admin xử lý hồ sơ trước khi văn bản được đưa vào kho tra cứu.

Chức năng cần có:

| Chức năng | Ghi chú |
|---|---|
| Tải DOCX mới | Có thể chọn preset từ danh sách corpus |
| Nhập thông tin văn bản | Tiêu đề, số hiệu, loại, cơ quan, ngày ban hành, ngày hiệu lực, ngày hết hiệu lực |
| Nhập nguồn | Nguồn mặc định là `Thư viện pháp luật`, vẫn cho sửa |
| Sửa thông tin sau upload | Metadata nhập lúc upload được xem là đã duyệt nhưng admin vẫn sửa được |
| Kiểm tra quan hệ văn bản | Bắt buộc nếu là văn bản sửa đổi, thay thế, hướng dẫn hoặc văn bản nền |
| Duyệt tóm tắt chuẩn | AI tạo bản nháp, admin sửa và duyệt |
| Kiểm tra nội dung rủi ro | Bảng, biểu mẫu, phụ lục, ảnh, trích dẫn hoặc nội dung parse chưa chắc chắn |
| Công bố | Chỉ công bố khi không còn việc bắt buộc phải xử lý |

Không hiển thị các từ như `revision`, `node`, `canonical`, `embedding`, `parser`,
`blocker`, `answerable`, `review-only`. Thay bằng tiếng Việt dễ hiểu.

### 4.2 Kho văn bản

`Kho văn bản` là nơi admin quản lý văn bản đã công bố.

Thông tin cần hiển thị đầy đủ hơn `Tra cứu văn bản`:

| Nhóm | Thông tin |
|---|---|
| Thông tin chính | Tiêu đề, số hiệu, loại, cơ quan, nguồn, đường dẫn nguồn |
| Thời gian | Ngày ban hành, ngày hiệu lực, ngày hết hiệu lực |
| Tình trạng | Đang công bố, tạm ngừng, hết hiệu lực, được thay thế, bị bãi bỏ |
| Vai trò | Văn bản chính, văn bản sửa đổi/bổ sung, văn bản thay thế, văn bản hướng dẫn, văn bản căn cứ, tài liệu tham khảo, quy chuẩn/tài liệu kỹ thuật |
| Quan hệ | Sửa đổi, được sửa đổi bởi, thay thế, được thay thế bởi, hướng dẫn, căn cứ liên quan |
| Tóm tắt chuẩn | Bản đã được admin duyệt |
| File nguồn | Tên file, nguồn tải, ngày tải, tải file |
| Lịch sử xử lý | Người tải lên, ngày công bố, lần cập nhật gần nhất |
| Cảnh báo | Thiếu dữ liệu, quan hệ chưa chắc chắn, nguồn chưa đủ, ngày hết hiệu lực chưa rõ |

Hành động admin cần có:

| Hành động | Quy tắc |
|---|---|
| Xem chi tiết | Xem toàn bộ thông tin văn bản |
| Sửa thông tin | Cho sửa metadata đã công bố |
| Sửa quan hệ | Cho cập nhật quan hệ với văn bản khác |
| Thay file | Tạo hồ sơ xử lý mới trong `Duyệt văn bản` |
| Tạm ngừng sử dụng | Không bắt buộc nhập lý do |
| Khôi phục | Đưa từ `Tạm ngừng` về `Đang công bố`, không bắt buộc kiểm tra lại |
| Đánh dấu hết hiệu lực | Không bắt buộc nhập lý do |
| Đánh dấu được thay thế | Không bắt buộc nhập lý do |
| Đánh dấu bị bãi bỏ | Không bắt buộc nhập lý do |

### 4.3 Tra cứu văn bản

`Tra cứu văn bản` là nơi người dùng public tìm và đọc văn bản đã công bố.

Thông tin một văn bản cần có:

| Trường | Quy tắc hiển thị |
|---|---|
| Tiêu đề | Bắt buộc |
| Số hiệu | Bắt buộc |
| Loại | Bắt buộc |
| Cơ quan | Bắt buộc |
| Nguồn | Mặc định là `Thư viện pháp luật` |
| Ngày ban hành | Có |
| Ngày hiệu lực | Có |
| Ngày hết hiệu lực | Nếu trống hiển thị `Chưa có` |
| Tình trạng | Nên hiển thị để người dùng biết văn bản còn dùng được không |
| Tóm tắt chuẩn | Hiển thị bản đã duyệt |
| Quan hệ văn bản | Hiển thị bằng ngôn ngữ dễ hiểu |
| File nguồn | Có cảnh báo trước khi xem hoặc tải |

Quy tắc hiển thị:

| Loại văn bản | Mặc định có hiện không? |
|---|---|
| Đang công bố | Có |
| Tạm ngừng | Không |
| Hết hiệu lực | Không, trừ khi bật bộ lọc hoặc tìm đúng số hiệu |
| Được thay thế | Không, trừ khi bật bộ lọc hoặc tìm đúng số hiệu |
| Bị bãi bỏ | Không, trừ khi bật bộ lọc hoặc tìm đúng số hiệu |

## 5. Trạng Thái Văn Bản

| Trạng thái | Ý nghĩa | Public thấy không | Chatbot dùng không |
|---|---|---:|---:|
| `Đang công bố` | Văn bản đã được kiểm tra và được dùng chính thức trong hệ thống | Có | Có |
| `Tạm ngừng` | Dữ liệu trong hệ thống cần kiểm tra hoặc sửa lại | Không | Không |
| `Hết hiệu lực` | Văn bản ngoài đời đã hết hiệu lực | Chỉ khi lọc hoặc tìm đúng số hiệu | Chỉ khi hỏi lịch sử/thời điểm cũ |
| `Được thay thế` | Văn bản đã được văn bản khác thay thế | Chỉ khi lọc hoặc tìm đúng số hiệu | Chỉ khi hỏi lịch sử/thời điểm cũ |
| `Bị bãi bỏ` | Văn bản đã bị bãi bỏ | Chỉ khi lọc hoặc tìm đúng số hiệu | Chỉ khi hỏi lịch sử/thời điểm cũ |
| `Đang xử lý` | Hồ sơ chưa công bố | Không | Không |

`Tạm ngừng` không có nghĩa là văn bản ngoài đời hết hiệu lực. Nó chỉ có nghĩa là bản
dữ liệu trong hệ thống chưa đủ tin cậy để dùng.

## 6. Luồng Duyệt Và Công Bố

```text
Admin tải DOCX
-> Hệ thống đọc và tách nội dung
-> Admin kiểm tra thông tin văn bản
-> Admin kiểm tra quan hệ cần thiết
-> Admin duyệt tóm tắt chuẩn
-> Admin kiểm tra nội dung rủi ro nếu có
-> Admin công bố vào kho văn bản
-> Người dùng tra cứu được
-> Chatbot được phép dùng để trả lời
```

Điều kiện công bố:

| Điều kiện | Bắt buộc |
|---|---:|
| Có file nguồn | Có |
| Có tiêu đề | Có |
| Có số hiệu | Có |
| Có loại văn bản | Có |
| Có cơ quan ban hành | Có |
| Có ngày ban hành | Có |
| Có ngày hiệu lực | Có |
| Có tóm tắt chuẩn đã duyệt | Có |
| Có quan hệ bắt buộc nếu là văn bản sửa đổi/thay thế/hướng dẫn hoặc cần căn cứ liên quan | Có |
| Nội dung rủi ro đã được xử lý | Có |

## 7. Quan Hệ Văn Bản

Quan hệ giúp hệ thống hiểu văn bản nào sửa đổi, thay thế, hướng dẫn hoặc làm căn cứ
cho văn bản nào.

| Quan hệ | Cách hiển thị |
|---|---|
| Sửa đổi | `Sửa đổi văn bản...` |
| Được sửa đổi bởi | `Được sửa đổi bởi văn bản...` |
| Thay thế | `Thay thế văn bản...` |
| Được thay thế bởi | `Được thay thế bởi văn bản...` |
| Hướng dẫn | `Hướng dẫn văn bản...` |
| Được hướng dẫn bởi | `Được hướng dẫn bởi văn bản...` |
| Căn cứ liên quan | `Là căn cứ liên quan cho...` |

Quy tắc bắt buộc:

| Loại văn bản | Có bắt buộc chọn quan hệ trước khi công bố không? |
|---|---:|
| Văn bản sửa đổi | Có |
| Văn bản thay thế | Có |
| Văn bản hướng dẫn | Có |
| Văn bản căn cứ | Có nếu hồ sơ cần liên kết với văn bản nguồn |
| Văn bản chính độc lập | Không |

## 8. Xử Lý Bảng, Biểu Mẫu, Phụ Lục, Ảnh, Trích Dẫn

| Nội dung | Cách xử lý |
|---|---|
| Văn bản thường | Dùng để trả lời nếu thuộc phần nội dung chính |
| Bảng trong điều/khoản/điểm | Mặc định dùng để trả lời; đưa vào review nếu hệ thống không chắc vị trí |
| Biểu mẫu trong điều/khoản/điểm | Mặc định dùng để trả lời nếu đã có chữ đọc được |
| Bảng trong phụ lục | Mặc định chỉ để đối chiếu, không dùng trả lời nếu chưa duyệt kỹ |
| Biểu mẫu trong phụ lục | Mặc định chỉ để đối chiếu |
| Ảnh | Không dùng để trả lời nếu chưa có mô tả chữ đã được duyệt |
| Quốc hiệu, tiêu ngữ, nơi nhận, người ký | Lưu để đối chiếu, không đưa vào phần trả lời pháp lý |
| Trích dẫn cuối trang/cuối văn bản | Lưu để đối chiếu; không dùng như căn cứ chính nếu chưa được liên kết rõ |

Khi hệ thống không xác định chắc bảng hoặc biểu mẫu thuộc điều/khoản hay phụ lục,
phải đưa vào `Nội dung cần kiểm tra kỹ` trong màn hình `Duyệt văn bản`.

## 9. Tóm Tắt

### 9.1 Tóm tắt chuẩn

Tóm tắt chuẩn là bản tóm tắt cố định của một văn bản.

Quy tắc:

| Quy tắc | Chốt |
|---|---|
| AI tạo bản nháp | Có |
| Admin sửa và duyệt | Có |
| Lưu vào database | Có |
| Mọi người xem cùng một bản | Có |
| Chỉ tóm tắt văn bản gốc đang xem | Có |
| Không tự tổng hợp nội dung hiện hành sau sửa đổi | Có |

### 9.2 Tóm tắt động

Tóm tắt động là câu trả lời realtime theo câu hỏi của người dùng.

Ví dụ:

| Câu hỏi | Cách xử lý |
|---|---|
| `Tóm tắt quy định liên quan xe tải dưới 3,5 tấn` | Tìm căn cứ phù hợp rồi tóm tắt |
| `Tóm tắt Điều 15 dưới góc nhìn doanh nghiệp` | Tìm đúng điều và diễn giải theo góc nhìn được hỏi |
| `Tóm tắt nội dung hiện hành sau sửa đổi` | Dùng văn bản gốc và văn bản sửa đổi đã công bố |

Tóm tắt động phải có căn cứ. Nếu không tìm thấy căn cứ, phải xin lỗi và nói chưa tìm
thấy thông tin phù hợp trong kho dữ liệu.

## 10. Chatbot

Chatbot chỉ dùng kho dữ liệu đã công bố.

Quy tắc trả lời:

| Tình huống | Cách trả lời |
|---|---|
| Có căn cứ rõ | Trả lời ngắn gọn, có điều/khoản hoặc phần văn bản liên quan |
| Chỉ có một phần căn cứ | Trả lời phần có trong kho, nói rõ phần chưa tìm thấy |
| Không tìm thấy văn bản theo số hiệu | Xin lỗi, nói chưa tìm thấy số hiệu đó trong kho dữ liệu |
| Không đủ căn cứ | Xin lỗi, nói chưa đủ căn cứ để trả lời chắc chắn |
| Câu hỏi ngoài phạm vi | Nói rõ kho dữ liệu hiện chỉ phục vụ lĩnh vực giao thông vận tải đường bộ |
| Hỏi mơ hồ về thời điểm | Hỏi lại mốc thời gian nếu cần |

Chatbot không được trả lời dựa trên:

| Không được dùng | Lý do |
|---|---|
| Văn bản đang xử lý | Chưa công bố |
| Văn bản tạm ngừng | Dữ liệu cần kiểm tra |
| Văn bản bị từ chối | Không đủ tin cậy |
| Nội dung ảnh chưa có mô tả duyệt | Không có căn cứ chữ |
| Bảng/phụ lục chưa xác định chắc | Dễ dẫn sai ngữ cảnh |
| Dữ liệu cũ chưa được upload lại | Không thuộc kho dữ liệu mới |

## 11. Xem Và Tải File Nguồn

Khi người dùng hoặc admin xem/tải bản sao văn bản, giao diện phải hiển thị cảnh báo:

```text
Bản này phục vụ tra cứu trong hệ thống. Khi sử dụng cho mục đích pháp lý hoặc chính
thức, vui lòng đối chiếu với nguồn văn bản chính thức.
```

File nguồn nên được lưu riêng tư. Đường dẫn tải xuống nên có thời hạn, không public
vĩnh viễn.

## 12. Dọn Dữ Liệu Cũ

Chính sách:

| Hạng mục | Cách xử lý |
|---|---|
| Dữ liệu văn bản cũ | Xóa khỏi luồng sử dụng chính |
| Chunk cũ | Xóa hoặc vô hiệu hóa |
| Embedding cũ | Xóa hoặc vô hiệu hóa |
| File nguồn cũ | Không giữ lại |
| Lịch sử chat/citation cũ | Không giữ lại |
| API cũ | Không để chatbot hoặc giao diện public gọi nữa |
| Giao diện cũ chỉ phục vụ kho cũ | Gỡ hoặc nối vào luồng mới |

Trước khi xóa dữ liệu thật, nên tạo backup database để có điểm quay lại nếu triển
khai gặp lỗi.

## 13. Tiêu Chí Hoàn Thành

Kho văn bản hợp nhất được xem là hoàn thành khi:

| Tiêu chí | Đạt |
|---|---:|
| Không còn nút hoặc màn hình riêng cho kho phiên bản cũ/mới | Có |
| `Duyệt văn bản` xử lý được upload, review, công bố | Có |
| `Kho văn bản` quản lý được văn bản đã công bố và đổi trạng thái | Có |
| `Tra cứu văn bản` chỉ hiển thị dữ liệu public phù hợp | Có |
| Chatbot chỉ dùng văn bản `Đang công bố` | Có |
| Văn bản `Tạm ngừng` không được public và không dùng để trả lời | Có |
| Dữ liệu cũ không còn tham gia trả lời | Có |
| Tất cả nhãn giao diện là tiếng Việt có dấu, dễ hiểu | Có |
| Tóm tắt chuẩn và tóm tắt động được tách rõ | Có |
| Bảng, biểu mẫu, phụ lục, ảnh, trích dẫn có quy tắc xử lý rõ | Có |
| Có cảnh báo khi xem/tải file nguồn | Có |
| Có kiểm thử cho tra cứu, duyệt, công bố, tạm ngừng và chatbot | Có |
