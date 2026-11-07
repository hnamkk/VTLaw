# Wireframes Và Hành Vi UI Hiện Hành
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

| Mục | Nội dung |
|---|---|
| Phạm vi | Public, user và admin UI sau R1-R6 |
| Frontend | Next.js, React, Tailwind CSS, Be Vietnam Pro |
| Cập nhật gần nhất | 06/07/2026 |

---

## 1. Điều hướng chính

| Vai trò | Mục hiển thị |
|---|---|
| Public | Tra cứu văn bản, Hỏi đáp pháp luật, Đăng nhập, Đăng ký |
| USER | Tra cứu văn bản, Hỏi đáp pháp luật, Thông báo, Đã lưu |
| ADMIN | Nhóm USER và nhóm Quản trị: Kho văn bản, Duyệt văn bản, Chất lượng AI, Người dùng |

Admin API vẫn có prefix tương thích nội bộ, nhưng UI chỉ dùng nhãn nghiệp vụ như `Kho văn bản` và `Duyệt văn bản`.

---

## 2. Public: Tra cứu văn bản

- Danh sách chỉ hiển thị văn bản đang công bố.
- Văn bản tạm ngừng không xuất hiện ở public surface.
- Ô tìm kiếm hỗ trợ tiêu đề, số hiệu và cơ quan ban hành.
- Kết quả ưu tiên bố cục gọn, dễ quét: loại văn bản, tiêu đề, cơ quan ban hành, ngày hiệu lực, trạng thái và hành động mở nguồn.
- Khi mở rộng một thẻ văn bản, UI hiển thị thêm `Quan hệ văn bản` nếu API trả quan hệ đã duyệt. Phần này là read-only, có số lượng quan hệ, loại quan hệ, chiều quan hệ và văn bản liên quan theo số hiệu/tiêu đề; nếu không có quan hệ thì không render khối trống.
- Khi mở file nguồn, UI phải nhắc người dùng đối chiếu với nguồn chính thức.

## 3. Public: Hỏi đáp pháp luật

- Chat hỗ trợ khách public và người dùng đã đăng nhập.
- Câu trả lời pháp lý phải có căn cứ hoặc thông báo thiếu căn cứ.
- Disclaimer là bắt buộc cho nội dung pháp lý.
- Citation có thể mở lại metadata/source lịch sử để đối chiếu provenance.
- Chatbot không dùng văn bản tạm ngừng để trả lời câu hỏi mới.
- Khu `Thông tin bổ sung` của chat hiển thị `answer_mode`, `risk_level`, `confidence` và tách ba nhóm nguồn: `provision_citations` cho căn cứ Điều/Khoản hiện hành, `document_sources` cho tóm tắt/metadata tổng quan, `historical_references` cho quy định lịch sử với cảnh báo không phải căn cứ hiện hành.
- Panel chat không hiển thị raw UUID/internal id cho người dùng; căn cứ Điều/Khoản dùng nhãn tự nhiên như `Căn cứ 1`, còn chi tiết văn bản hiển thị qua tiêu đề/nguồn/citation khi có.
- Khi backend trả `answer_mode=clarification_needed`, khu `Thông tin bổ sung` hiển thị rõ câu hỏi cần làm rõ; metadata này cũng được giữ lại khi người dùng mở lại lịch sử phiên.

## 4. USER: Thông báo và Đã lưu

- `Thông báo` hiển thị danh sách, trạng thái đã đọc/chưa đọc và SSE realtime khi có thông báo mới.
- `Đã lưu` tập trung vào phiên hội thoại đã lưu, không trộn với bookmark văn bản riêng.
- Khách chưa đăng nhập thấy hướng dẫn đăng nhập mềm mại thay vì lỗi kỹ thuật.

## 5. ADMIN: Kho văn bản

Mục tiêu của màn này là quản lý inventory văn bản đã hoặc từng công bố.

Các phần chính:

- hero Kho dùng bố cục một cột full-width, không lặp nút `Thêm văn bản`; thao tác thêm mới thuộc màn `Duyệt văn bản`
- bộ lọc theo trạng thái và từ khóa
- bảng/danh sách văn bản
- trạng thái hiển thị: `Đang công bố`, `Tạm ngừng`, `Hết hiệu lực`, `Được thay thế`, `Bị bãi bỏ`
- khu sửa thông tin văn bản
- khu quản lý quan hệ văn bản
- hành động đổi trạng thái
- hành động `Thay file nguồn` trong chi tiết văn bản, mở modal upload để tạo hồ sơ thay file trong `Duyệt văn bản`; modal có header cố định, body cuộn độc lập và footer bám đáy để dùng được trên desktop/mobile
- tải file nguồn kèm cảnh báo đối chiếu

`Tạm ngừng` đồng nghĩa với:

- không hiện public
- không dùng cho chatbot
- vẫn giữ lại metadata/source lịch sử phục vụ audit và citation cũ

Khi admin thay file nguồn, bản đang công bố vẫn tiếp tục phục vụ trang tra cứu và chatbot. File mới chỉ trở thành dữ liệu public/chat sau khi hồ sơ thay file được duyệt và đưa vào kho. Form thay file bắt buộc xác nhận đúng số hiệu văn bản; nếu các metadata pháp lý chính bị thay đổi, UI yêu cầu admin xác nhận sẽ rà lại quan hệ trong hồ sơ mới trước khi tạo bản nháp.

## 6. ADMIN: Duyệt văn bản

Màn này là nơi duy nhất để tải DOCX mới và đưa hồ sơ qua review trước khi công bố.

Flow hiện hành ưu tiên một luồng duyệt chính rõ ràng:

- dùng cùng ngôn ngữ bố cục với `Kho văn bản`: hero ngắn, toolbar tìm kiếm, danh sách hồ sơ và accordion xem nhanh
- mặc định mở nhóm `Đang xử lý`; khi nhóm này trống, hiển thị empty state `Không còn hồ sơ cần duyệt` và cho phép chuyển sang `Đã đưa vào kho` để xem lịch sử/tham chiếu
- nút `Thêm văn bản` mở hộp thoại tạo hồ sơ thay vì đẩy form upload ra ngay trên trang; form dùng một grid liền mạch, đặt mẫu điền nhanh phía trên chọn file và căn span các field dài để hạn chế khoảng trống
- khi tạo hồ sơ, hộp thoại hiển thị tiến trình theo các bước tải file, tách nội dung, tạo đề xuất và mở hồ sơ duyệt; trong lúc xử lý không cho đóng modal bằng backdrop; khi mở hồ sơ mới, trạng thái tiến trình hoặc thông báo thành công từ hồ sơ trước phải được dọn khỏi modal
- tóm tắt và quan hệ văn bản được xử lý sau khi parse trong hồ sơ duyệt: tóm tắt sinh từ nội dung nguồn và có thể chỉnh trong `Thông tin văn bản`, còn quan hệ cần chọn văn bản liên quan bằng combobox trước khi đưa vào kho nếu workflow yêu cầu
- mỗi hồ sơ có nút `Chỉnh sửa`; khi bấm sẽ mở hộp thoại lớn để xử lý chi tiết
- card hồ sơ trong danh sách ưu tiên “việc cần xử lý trước”: hàng badge chỉ còn trạng thái công bố, loại văn bản, số hiệu và số việc còn lại; dưới tiêu đề là cơ quan ban hành và ngày hiệu lực; cạnh phải chỉ giữ icon chỉnh sửa và mũi tên mở rộng
- phần chi tiết trong hộp thoại tiếp tục chia theo accordion: thông tin văn bản, quan hệ văn bản, tóm tắt, nội dung cần xem kỹ, lịch sử xử lý
- accordion `Lịch sử xử lý` sắp sự kiện mới nhất trước và phân trang 5 bản ghi mỗi trang để modal không kéo dài quá mức
- accordion `Thông tin văn bản` là form chỉnh sửa thật cho các field chính như tiêu đề, tóm tắt, số hiệu, loại, vai trò, cơ quan ban hành, các mốc ngày và metadata nguồn; không chỉ là danh sách read-only
- khi lưu trong `Duyệt văn bản`, hồ sơ `draft` sẽ tạo/cập nhật metadata proposal rồi duyệt ngay các trường vừa chỉnh; hồ sơ đã ở trong kho cập nhật trực tiếp theo `document_id` mà không bắt admin rời sang màn khác
- các mục parser đã tự xác nhận hoặc đánh dấu chỉ để đối chiếu không hiện lại như việc cần duyệt; modal chỉ mở sẵn accordion còn phát sinh việc admin phải xử lý
- nút `Đưa vào kho` là điểm kiểm tra cuối: nếu còn việc cần xử lý, UI không công bố và tự mở phần tương ứng; nếu hồ sơ đã đủ điều kiện, UI yêu cầu admin xác nhận trước khi thực hiện
- không hiển thị khung trạng thái riêng khi không còn đề xuất thông tin cần xác nhận
- phần tổng quan hồ sơ nằm giữa theo một cột full-width, không dành cột riêng cho thao tác
- hộp thoại chỉnh sửa chỉ giữ hành động `Đưa vào kho` và `Tải file nguồn`; hai nút nằm cùng hàng, căn phải ở cuối nội dung; trên mobile dùng lưới hai cột và có thể co theo chiều rộng màn hình
- body của hộp thoại chỉnh sửa cuộn độc lập; cụm hành động cuối modal bám đáy để không bị cắt khi accordion dài
- các thao tác ghi hoặc phá hủy như lưu thông tin, đưa vào kho, sửa/loại bỏ quan hệ và đưa mục đã kiểm tra về xử lý lại dùng hộp thoại xác nhận tùy biến thống nhất, không dùng hộp xác nhận native của trình duyệt; riêng tạo quan hệ thực hiện trực tiếp vì quan hệ mới vẫn ở trạng thái chờ duyệt và có hành động sửa/loại bỏ riêng
- khi đổi trạng thái trong `Kho văn bản`, ô ghi chú nằm ngay trong hộp xác nhận tùy biến và được lưu cùng lịch sử xử lý; UI không mở thêm prompt native của trình duyệt
- hồ sơ đã đưa vào kho và không còn việc chờ xử lý hiển thị `Đã kiểm tra`; không gắn nhãn `Đang kiểm tra` gây hiểu nhầm phải duyệt lại
- phần tổng quan chỉ hiển thị các việc còn cần xử lý, không lặp lại thống kê các mục đã xác nhận hoặc cách dùng nội dung
- cảnh báo trong modal duyệt được hợp nhất từ điều kiện chặn công bố và cảnh báo bộ tách nội dung, Việt hóa rồi khử trùng theo nội dung trước khi hiển thị; cùng một cảnh báo chỉ xuất hiện một lần
- mobile dùng full-screen sheet, header gọn, title giới hạn dòng và body cuộn bên trong modal để tránh thao tác chiếm hết màn đầu
- quan hệ văn bản dùng trường chọn/tìm trên toàn bộ hồ sơ theo số hiệu hoặc tiêu đề, gồm cả hồ sơ chưa đưa vào kho và luôn loại chính văn bản đang mở; UI không yêu cầu admin nhập id nội bộ
- `Duyệt văn bản` hiển thị quan hệ chờ xử lý trước và gom quan hệ đã xác nhận vào nhóm thu gọn; không dùng trạng thái “không có quan hệ” khi chỉ đơn giản là không còn quan hệ chờ duyệt
- quan hệ đi vào chỉ hiển thị để đối chiếu tại văn bản đích; việc chỉnh sửa và duyệt được thực hiện tại văn bản nguồn
- các field enum như loại văn bản, vai trò văn bản, loại quan hệ dùng cùng một kiểu dropdown bọc icon để nhãn và mũi tên luôn thẳng hàng giữa desktop và mobile
- tiêu đề văn bản và tóm tắt dùng textarea tự mở rộng theo nội dung; tiêu đề giới hạn 2-3 dòng để soát nhanh trên desktop và không chiếm quá nhiều không gian trên mobile

Các nhãn hiển thị cho admin phải dùng tiếng Việt nghiệp vụ. Không lộ raw field như `document_type`, `document_role`, `NGHI_DINH` hoặc tên route nội bộ.

Input file/date phải có label và helper tiếng Việt rõ ràng. Nếu dùng control native, UI phải bao bọc đủ để người dùng hiểu định dạng và mục đích.

Hai màn `Kho văn bản` và `Duyệt văn bản` dùng skeleton ngay trong vùng danh sách khi tải, kèm nhãn `Đang tải danh sách...`; không phủ lớp mờ lên toàn trang. Nếu request kéo dài quá ngưỡng chờ, vùng danh sách hiển thị cảnh báo tiếng Việt và cho phép người dùng chủ động làm mới. Các ô ngày rỗng hiển thị `Chọn ngày`, vẫn giữ native date picker và mô tả định dạng ngày-tháng-năm cho công nghệ hỗ trợ.

Trên mobile, các thẻ thống kê/trạng thái của cả hai màn xếp thành lưới hai cột, co theo chiều rộng viewport và không dùng card bị cắt lửng để gợi ý cuộn ngang.

## 7. ADMIN: Chất lượng AI

Dashboard vận hành tập trung vào:

- tình trạng tổng quan
- mức bao phủ dữ liệu đánh giá
- vấn đề cần xử lý
- lịch sử kiểm chuẩn
- bằng chứng liên quan tới câu trả lời/căn cứ

Text hiển thị cho admin phải dùng tiếng Việt nghiệp vụ. Thuật ngữ kỹ thuật chỉ xuất hiện khi thật cần thiết và đã có nhãn dễ hiểu đi kèm.

## 8. ADMIN: Người dùng

- Danh sách người dùng hỗ trợ tìm theo tên hoặc email.
- Admin có thể tạo, cập nhật, khóa mềm và đặt lại mật khẩu.
- Không hiển thị mật khẩu hoặc token trong UI/log.

## 9. Responsive và accessibility

- Desktop ưu tiên mật độ thông tin, bảng và panel thao tác rõ ràng.
- Mobile dùng panel chuyển bước hoặc drawer/sidebar gọn, tránh che nội dung chính.
- Các control tương tác có label, focus state và keyboard path.
- Text trong button/card không được tràn hoặc chồng lên nội dung khác.

## 10. Bằng chứng UI

Bộ E2E hiện hành chụp desktop/mobile cho public và admin:

- `e2e-snapshots-live/`
- `e2e-admin-snapshots/`

E2E fail nếu còn overlay lỗi ứng dụng, mojibake, text cấm, active view sai hoặc network status bất thường.
Regression quản trị còn đối chiếu `relation_count` theo mọi `document_id` xuất hiện ở cả API Kho và API Duyệt, qua toàn bộ trang dữ liệu và trạng thái hồ sơ; không phụ thuộc số hiệu văn bản cố định.
Snapshot Kho/Duyệt chỉ được chụp sau khi loading cục bộ và skeleton danh sách đã kết thúc, để số liệu và empty state trong artifact phản ánh response thật.
