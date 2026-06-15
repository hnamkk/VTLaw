# Quy Trình Cập Nhật Kho Văn Bản
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

| Mục | Nội dung |
|---|---|
| Phạm vi | Upload, duyệt, công bố, tạm ngừng và quản lý văn bản |
| Source of truth | PostgreSQL + storage cục bộ/object storage |
| Cập nhật gần nhất | 06/07/2026 |

---

## 1. Mục tiêu

Mọi thay đổi kho văn bản phải đi qua review của admin trước khi trở thành dữ liệu dùng cho public/chat. Runtime hiện hành chỉ dùng một kho văn bản đang công bố cho public/chat.

---

## 2. Các bề mặt quản trị

| Màn hình | Vai trò |
|---|---|
| `Duyệt văn bản` | Tải DOCX, rà metadata, rà nội dung, duyệt tóm tắt, công bố revision |
| `Kho văn bản` | Quản lý inventory văn bản đã hoặc từng công bố, sửa metadata và đổi trạng thái quản trị |

Prefix `/api/v1/admin/kb-v2` vẫn được giữ để tương thích contract nội bộ. UI quản trị phải hiển thị bằng tên trung lập `Kho văn bản`, không lộ nhãn `kb-v2`.

---

## 3. Luồng upload và review

### 3.1 Upload

`POST /api/v1/admin/kb-v2/revisions/upload` hiện:

1. Nhận DOCX và metadata nguồn/văn bản từ form admin.
2. Lưu source asset vào storage hiện hành.
3. Tính checksum để chặn upload trùng.
4. Tạo revision `draft`, source asset, canonical nodes, metadata proposals, summary draft và audit event.

`POST /api/v1/admin/kb-v2/documents/{document_id}/replacement-revisions/upload` dùng cho thao tác `Thay file nguồn` trong `Kho văn bản`. Endpoint này tạo revision `draft` mới trên cùng `document_id` đã hoặc từng công bố, tăng `revision_number`, tách lại node từ file mới và ghi audit event `created` với chế độ upload thay file. Revision đang công bố không bị sửa trực tiếp, nên public/chatbot vẫn dùng bản cũ cho tới khi hồ sơ thay file được duyệt.

Metadata của hồ sơ thay file cũng không ghi trực tiếp vào document đang công bố trong giai đoạn review. Các proposal đã duyệt chỉ được áp dụng lên document khi revision thay file qua toàn bộ gate và được publish, để public/chatbot không thấy metadata mới đi kèm nội dung cũ.

Sau khi upload thành công, frontend chuyển sang `Duyệt văn bản` bằng `revision_id` của revision mới hoặc revision trùng file mà API trả về. Form thay file khóa thao tác đóng trong lúc xử lý, hiển thị tiến trình `Tải file` → `Tách nội dung` → `Tạo đề xuất` → `Mở hồ sơ`, và yêu cầu admin xác nhận đúng số hiệu; nếu metadata chính thay đổi thì admin phải xác nhận sẽ rà lại quan hệ trước khi tạo hồ sơ.

### 3.2 Review

Admin duyệt qua các nhóm việc:

- metadata proposals
- canonical nodes
- nhóm mục cần xem kỹ
- quan hệ văn bản
- tóm tắt chuẩn

Mọi quyết định review đều ghi vào `kb_v2_review_events`.

UI `Duyệt văn bản` hiện hành tổ chức lại theo flow chính:

- dùng cùng cấu trúc màn hình với `Kho văn bản`: hero ngắn, thanh tìm kiếm, danh sách hồ sơ, accordion xem nhanh
- danh sách mặc định lọc revision `draft` thuộc nhóm `Đang xử lý`; nếu không còn hồ sơ, UI hiển thị empty state rõ ràng và cung cấp lối chuyển sang nhóm `Đã đưa vào kho` để tra cứu lịch sử
- API list hồ sơ trả thêm `issuing_authority`, `effective_date`, `expiry_date`, `pending_metadata_count`, `pending_relations_count`, `pending_risky_nodes_count`, `summary_status`, `publish_blockers_count`, `is_ready_to_publish` và `relation_count` để card danh sách không phải gọi detail chỉ để dựng trạng thái tổng quan
- form upload chỉ xuất hiện trong hộp thoại `Thêm văn bản`; bố cục form là một grid liền mạch, đặt mẫu điền nhanh phía trên chọn file và căn span các field dài để admin không phải quét field lộn xộn hoặc gặp khoảng trống lớn
- trong lúc tạo hồ sơ, UI hiển thị tiến trình tải file, tách nội dung, tạo đề xuất và mở hồ sơ; thao tác đóng modal bị khóa cho tới khi request kết thúc; khi chuyển sang hồ sơ mới, modal duyệt không giữ lại tiến trình hoặc thông báo thành công của hồ sơ trước
- sau khi upload thành công, tóm tắt chuẩn và quan hệ văn bản được xử lý trong modal duyệt của chính hồ sơ vừa tạo; form upload không tạo quan hệ giả vì quan hệ cần chọn văn bản đích từ kho sau khi có hồ sơ
- thao tác `Chỉnh sửa` mở hộp thoại lớn để admin xử lý trọn một hồ sơ mà không rời danh sách
- card hồ sơ ưu tiên hiển thị việc cần xử lý trước: badge trạng thái, loại văn bản, số hiệu và số việc còn lại ở hàng đầu; dưới tiêu đề là cơ quan ban hành và ngày hiệu lực; action cạnh phải chỉ giữ nút chỉnh sửa và mũi tên mở rộng
- dòng meta thời gian trên card dùng `uploaded_at` như mốc `Tạo hồ sơ`; chỉ khi có review event thật sau bước tạo mới dùng `updated_at` để hiển thị `Cập nhật gần nhất`
- modal chỉnh sửa chỉ giữ action công bố ban đầu và tải file nguồn; thao tác tạm ngừng, khôi phục hoặc đổi trạng thái sau công bố thuộc màn `Kho văn bản`; accordion xem nhanh của card danh sách không lặp lại các nút này
- phần tổng quan của modal chỉ hiển thị số việc còn cần xử lý, không hiển thị dải thống kê các mục đã xác nhận hoặc cách dùng nội dung
- accordion `Thông tin văn bản` trong modal là form chỉnh sửa đầy đủ cho các field chính của hồ sơ thay vì chỉ hiển thị danh sách metadata read-only
- khi admin lưu `Thông tin văn bản`, revision `draft` sẽ tạo/cập nhật metadata proposal rồi duyệt ngay; revision đã ở trong kho cập nhật trực tiếp văn bản đang quản lý theo `document_id`
- thông tin cần xác nhận được nhóm bằng accordion để rút ngắn quãng quét mắt khi duyệt
- accordion `Lịch sử xử lý` hiển thị sự kiện mới nhất trước và phân trang 5 bản ghi mỗi trang
- UI chỉ đưa các mục còn cần admin quyết định vào danh sách xử lý; mục parser đã tự xác nhận hoặc đánh dấu chỉ để đối chiếu được tính vào nhóm đã xử lý, không yêu cầu admin duyệt lại
- API chi tiết hồ sơ trả các trường tổng hợp như `pending_metadata`, `pending_relations`, `pending_risky_nodes`, `resolved_risky_nodes` và `is_ready_to_publish`; UI ưu tiên dùng các trường này thay vì tự suy diễn từ node thô
- mục đã kiểm tra được gom vào accordion đóng mặc định với số lượng và quyết định hiện tại; chỉ mở form khi admin chọn sửa quyết định
- trong mục cần xem kỹ, UI chỉ hiện hai lựa chọn chính trực tiếp là dùng cho trả lời hoặc chỉ để đối chiếu; các quyết định ít dùng hơn được đưa vào menu phụ để giảm nhiễu
- khi admin chọn `Đưa vào kho`, UI kiểm tra điều kiện hiện tại: hồ sơ còn việc cần xử lý bị chặn và phần tương ứng được tự mở; hồ sơ đã đủ điều kiện phải qua hộp thoại xác nhận trước khi gọi API công bố; tiến trình hoàn tất chỉ hiện ngắn rồi tự ẩn để không lẫn sang hồ sơ kế tiếp
- UI không hiển thị khung trạng thái riêng khi không còn đề xuất thông tin cần xác nhận
- phần tổng quan trong modal chỉnh sửa dùng một cột full-width; cụm công bố và tải file nguồn nằm cùng hàng, căn phải ở cuối nội dung; mobile dùng full-screen sheet và lưới thao tác hai cột
- body modal cuộn độc lập và footer thao tác bám đáy bên trong modal, nên action vẫn truy cập được khi accordion có nội dung dài
- mọi thao tác làm thay đổi dữ liệu quan trọng trong modal dùng cùng một hộp thoại xác nhận tùy biến: lưu thông tin, công bố, sửa/loại bỏ quan hệ và đưa mục nội dung đã xử lý về trạng thái cần xem lại; tạo quan hệ không hỏi xác nhận vì bản ghi mới còn phải được duyệt và có thể sửa hoặc loại bỏ ngay trong cùng luồng
- revision đã công bố và không còn metadata, quan hệ hoặc mục nội dung chờ xử lý hiển thị trạng thái `Đã kiểm tra`, không hiển thị `Đang kiểm tra`
- form upload và form duyệt dùng dropdown thống nhất cho loại/vai trò/loại quan hệ, với icon canh phải đồng nhất giữa desktop và mobile; quan hệ văn bản dùng combobox truy vấn toàn bộ hồ sơ theo số hiệu hoặc tiêu đề, gồm cả hồ sơ chưa công bố và loại chính văn bản đang mở; tiêu đề và tóm tắt dùng textarea tự mở rộng để soát nội dung dài
- UI hiển thị đầy đủ quan hệ đi và đến; chỉ quan hệ đi ra từ văn bản hiện tại được tính là việc chờ duyệt của hồ sơ, còn quan hệ đi vào là ngữ cảnh chỉ đọc
- backend chặn quan hệ tự liên kết và quan hệ trùng cùng văn bản nguồn, văn bản đích và loại quan hệ
- quan hệ đi đã xác nhận có thể được đưa về nhóm cần xử lý để sửa và duyệt lại; quan hệ tạo nhầm có thể bị loại bỏ sau xác nhận, đồng thời hệ thống ghi lịch sử xử lý

---

## 4. Điều kiện công bố

Một revision chỉ được công bố khi:

- có source asset hợp lệ
- metadata bắt buộc đã được duyệt
- không còn mục cần xem kỹ chưa có quyết định
- tóm tắt chuẩn đã được duyệt
- các quan hệ bắt buộc đã được duyệt nếu workflow yêu cầu
- nếu môi trường yêu cầu object storage thì source phải đáp ứng điều kiện đó

---

## 5. Công bố và tạm ngừng

### 5.1 Công bố

Khi qua toàn bộ gate:

1. Áp dụng metadata proposal đã duyệt của revision đang publish lên document.
2. Xác nhận revision có ít nhất một mục nội dung đã duyệt và được dùng cho hỏi đáp; mục chỉ để đối chiếu không được tính.
3. Tạo `kb_v2_retrieval_units` theo metadata và mốc hiệu lực vừa được chốt.
4. Sinh embedding cho phần nội dung đủ điều kiện trả lời.
5. Nếu cùng `document_id` đã có revision `published` hoặc `suspended`, chuyển các revision cũ sang `archived` và hạ retrieval units cũ về trạng thái lịch sử.
6. Đổi revision mới sang `published`.
7. Cập nhật trạng thái pháp lý của document theo mốc hiệu lực.
8. Ghi audit event `published`.

Yêu cầu công bố có thể được gửi lại an toàn sau timeout hoặc mất phản hồi. Nếu
revision đã `published`, backend trả chi tiết hiện tại với `200` và không lặp
bước tạo retrieval units/audit event; nhờ đó UI có thể đồng bộ lại nhãn thay vì
hiển thị lỗi `409` cho một thao tác thực tế đã hoàn tất.

Trước khi tạo retrieval units, hệ thống kiểm tra citation cho mọi mục đã duyệt và được dùng cho hỏi đáp. Citation phải được dựng từ `structured_content.article_num`, `structured_content.clause_num` và `structured_content.point_num`; nếu nhãn trích dẫn thiếu hoặc lệch Điều/Khoản/Điểm thì publish bị chặn. Với mục không có locator pháp lý chuẩn, nhãn fallback được nén trong giới hạn DB để không làm hỏng bước publish; các mục dùng cho hỏi đáp vẫn phải có citation Điều/Khoản/Điểm hợp lệ.

Các retrieval units đã công bố trước khi rule citation này được áp dụng có thể được audit bằng `python scripts/rebuild_kb_v2_citations.py`. Lệnh mặc định là dry-run, chỉ báo số unit lệch citation; chỉ khi truyền `--apply` script mới rebuild retrieval units và ghi audit event `updated`.

Khi cần sửa cây canonical của revision cũ sau thay đổi parser, dùng
`python scripts/rebuild_kb_v2_structure.py --revision-id <id>` để dry-run. Chỉ
truyền `--apply` sau khi đã backup database và báo cáo ánh xạ được toàn bộ node
hiện có. Script giữ ID và vector của node cũ, bổ sung node cấu trúc còn thiếu,
cập nhật lại trạng thái dùng cho hỏi đáp và ghi audit event `updated`; script từ
chối chạy nếu revision đã có liên kết phiên bản điều khoản.

### 5.2 Tạm ngừng

Tạm ngừng là fail-closed:

1. Đổi revision sang `suspended`.
2. Đổi `legal_status` của document sang `suspended`.
3. Hạ retrieval units liên quan sang trạng thái không dùng để trả lời.
4. Ghi audit event `suspended`.

Sau khi tạm ngừng hoặc đổi sang trạng thái lịch sử như `expired`, `replaced`, `annulled`:

- văn bản không còn hiện ở public surface hiện hành
- chatbot không còn dùng văn bản đó cho câu trả lời mới
- historical citation vẫn có thể mở metadata/source của câu trả lời cũ

---

## 6. Public surface sau công bố

Public surface hiện hành bao gồm:

- danh sách văn bản đang công bố
- chi tiết văn bản đang công bố
- file nguồn của bản đang công bố
- tóm tắt chuẩn
- tóm tắt động
- historical citation metadata/source

Quy tắc bắt buộc:

- chỉ văn bản đang công bố với `legal_status='active'` mới hiện public
- văn bản `suspended`, `expired`, `replaced` hoặc `annulled` không hiện public
- văn bản `suspended`, `expired`, `replaced` hoặc `annulled` không được dùng cho chatbot

---

## 7. Kho văn bản sau công bố

`Kho văn bản` dùng các route quản trị theo `document_id`:

- `GET /api/v1/admin/kb-v2/documents`
- `GET /api/v1/admin/kb-v2/documents/{document_id}`
- `PATCH /api/v1/admin/kb-v2/documents/{document_id}`
- `POST /api/v1/admin/kb-v2/documents/{document_id}/status`

Hành vi hiện hành:

- chỉ liệt kê văn bản đã hoặc từng công bố
- không trộn hồ sơ `draft` vào inventory này
- cho phép sửa metadata trực tiếp trên văn bản đã công bố
- cho phép đổi trạng thái quản trị như `active`, `suspended`, `expired`, `replaced`, `annulled`; chỉ `active` được dùng cho public/chat
- thao tác `Thay file nguồn` mở form upload ngay trong chi tiết văn bản, tạo hồ sơ thay file trong `Duyệt văn bản`; không sửa trực tiếp file, node hoặc retrieval unit của bản đang công bố
- modal thay file dùng body cuộn độc lập, footer sticky và handoff bằng `revision_id`, nên không bị cắt form trên mobile và không mở nhầm hồ sơ khi tiêu đề trùng hoặc gần giống nhau

---

## 8. Boundary với mã legacy

- Runtime public/chat không dùng `legal_documents` hoặc `document_chunks`.
- `admin_kb.py` không được mount trong runtime.
- `src.rag.retrieval.hybrid` là mã legacy, không phải đường retrieval đang chạy.
- Script publish/reconcile cũ bị chặn mặc định và chỉ chạy khi có `--legacy-allow`.
- Tên `kb_v2_*` được giữ ở schema nội bộ để tránh migration đổi tên lớn; không phải tên sản phẩm hiển thị cho người dùng.

---

## 9. Yêu cầu vận hành

- Chạy migration trước khi dùng workflow quản trị.
- Khi cần storage bắt buộc, dùng `KB_REQUIRE_OBJECT_STORAGE`.
- Trước mọi dọn dẹp dữ liệu hoặc file cũ phải có backup rõ ràng.
- Sau mỗi thay đổi hành vi workflow hoặc surface public/chat, phải cập nhật `docs/project/` và bài test liên quan.

## 10. Guard dữ liệu cấu trúc trước công bố

- Backend chặn publish nếu `clause` hoặc `point` không có node cha phù hợp trong cây canonical.
- Node Khoản/Điểm mồ côi phải được sửa bằng `scripts/rebuild_kb_v2_structure.py` sau khi đã backup database.
- Citation dry-run bằng `scripts/rebuild_kb_v2_citations.py` phải sạch trước khi coi batch rebuild là hoàn tất.
- Nếu một revision đã `published` được gọi publish lại, backend vẫn chạy các guard dữ liệu; chỉ khi không còn blocker thật thì `review_status` lệch mới được chuẩn hóa về `approved` mà không rebuild retrieval units.
