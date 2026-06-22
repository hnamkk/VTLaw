# Đặc Tả API
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

| Mục | Nội dung |
|---|---|
| Phiên bản API | `v1` |
| Base URL (dev) | `http://localhost:8000/api/v1` |
| Giao thức | HTTPS/REST + SSE |
| Xác thực | JWT Bearer cho route `USER` và `ADMIN` |
| Cập nhật gần nhất | 09/07/2026 |

---

## 1. Nguyên tắc chung

- Public documents, public source và chatbot chỉ dùng dữ liệu từ kho văn bản đang công bố với `legal_status='active'`.
- Văn bản `suspended`, `expired`, `replaced` hoặc `annulled` không xuất hiện ở surface public hiện hành và không được dùng cho chatbot.
- Chat historical/lifecycle chi di qua nhanh chuyen biet de tra metadata hoac `historical_references`; ngoai le nay khong lam rong active-only retrieval mac dinh.
- Prefix `/api/v1/admin/kb-v2` được giữ để tương thích contract nội bộ hiện có. Frontend phải bọc các route này bằng tên trung lập theo ngữ cảnh `Kho văn bản`.
- Tên bảng/model `kb_v2_*` chỉ là chi tiết schema nội bộ, không phải nhãn sản phẩm.
- Route legacy `admin_kb.py` không được mount trong runtime.

### 1.1 Mẫu lỗi

```json
{
  "detail": {
    "code": "KB_DOCUMENT_LIST_UNAVAILABLE",
    "message": "Hệ thống chưa thể tải danh sách văn bản trong kho. Vui lòng thử lại sau."
  }
}
```

Các thông báo fallback phải dùng tiếng Việt dễ hiểu; không để lộ `Internal Server Error` ra UI.

Runtime hiện tại của `Duyệt văn bản` dùng thêm hai fallback ổn định sau:

- `GET /admin/kb-v2/revisions`: nếu lỗi serialize hoặc lỗi nội bộ ngoài nhóm `HTTPException`, API trả `500` với `detail.code = KB_DOCUMENT_LIST_UNAVAILABLE` và thông điệp `Hệ thống chưa thể tải danh sách hồ sơ duyệt văn bản. Vui lòng thử lại sau.`
- `GET /admin/kb-v2/revisions/{revision_id}`: nếu lỗi serialize hoặc lỗi nội bộ ngoài nhóm `HTTPException`, API trả `500` với `detail.code = KB_REVISION_DETAIL_UNAVAILABLE` và thông điệp `Chưa thể mở chi tiết hồ sơ xử lý này. Vui lòng thử lại sau.`

---

## 2. Xác thực

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Đăng ký tài khoản |
| `POST` | `/auth/login` | Public | Đăng nhập |
| `GET` | `/auth/me` | USER | Lấy hồ sơ hiện tại |
| `PATCH` | `/auth/me` | USER | Cập nhật hồ sơ |
| `POST` | `/auth/change-password` | USER | Đổi mật khẩu |
| `POST` | `/auth/logout` | USER | Đăng xuất |

---

## 3. Chat và lịch sử hội thoại

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `POST` | `/chat/stream` | Public hoặc USER | Chat stream qua SSE |
| `GET` | `/chat/sessions` | USER | Danh sách phiên chat của chính người dùng |
| `GET` | `/chat/bookmarks` | USER | Danh sách phiên đã lưu |
| `GET` | `/chat/sessions/{session_id}/messages` | USER | Tin nhắn của một phiên |
| `PATCH` | `/chat/sessions/{session_id}/bookmark` | USER | Lưu hoặc đổi tên phiên |
| `DELETE` | `/chat/sessions/{session_id}/bookmark` | USER | Bỏ lưu phiên |
| `DELETE` | `/chat/sessions/{session_id}` | USER | Xóa phiên của chính người dùng |

### 3.1 Contract quan trọng của `POST /chat/stream`

- Guest chat vẫn được hỗ trợ, nhưng chịu public rate limit.
- Nếu có JWT hợp lệ, lịch sử chat được lưu vào `qa_sessions` và `qa_messages`.
- Assistant message mới lưu thêm `response_metadata` trong `qa_messages` để khi mở lại lịch sử, `GET /chat/sessions/{session_id}/messages` trả đúng risk/mode/citation taxonomy như SSE `done`; message cũ chưa có metadata vẫn được backend suy luận fallback từ content/citations.
- SSE `done` trả thêm metadata audit như `guardrail_triggered`, `guardrail_stage`, `guardrail_reason`.
- SSE `done` và `GET /chat/sessions/{session_id}/messages` cùng dùng response metadata schema ổn định:
  - `risk_level`
  - `answer_mode`
  - `confidence { level, reason }`
  - `provision_citations`
  - `document_sources`
  - `historical_references`
  - `clarification_question`
- Field legacy `citations` vẫn được giữ để tương thích ngược với client hiện tại.
- `provision_citations` chỉ map từ citation đã qua verifier khi citation còn `status='active'` và `verification_status` thuộc `verified` hoặc `partial`.
- `historical_references` không được trộn vào `provision_citations`; nếu có metadata lịch sử thì chúng đi ở field riêng.
- `document_sources` là field nguồn tổng quan cho các nhánh `summary`, `document_lookup`, `effective_status`; không bắt buộc ở mọi câu trả lời đã có `provision_citations`.
- `answer_mode` phản ánh nhánh trả lời hiện hành:
  - `direct`: câu trả lời pháp lý trực tiếp
  - `summary`: tóm tắt văn bản
  - `historical`: câu trả lời đang đi theo intent so sánh/lịch sử
  - `clarification_needed`: câu hỏi cần làm rõ
  - `multiple_possibilities`: câu hỏi thiên về chiến lược hoặc phụ thuộc thêm dữ kiện, không nên coi là tư vấn trực tiếp
  - `insufficient_evidence`: guardrail thiếu căn cứ
  - `out_of_scope`: từ chối ngoài phạm vi hoặc prompt injection
- `risk_level` được gán bằng rule deterministic từ pipeline state, không được chèn vào answer text:
  - `low`: tra cứu quy định/định nghĩa rõ, có căn cứ active phù hợp
  - `medium`: thủ tục, câu hỏi cần làm rõ, lịch sử hoặc thiếu căn cứ
  - `high`: mức phạt, tranh chấp, khiếu nại/khởi kiện hoặc câu hỏi mang tính chiến lược pháp lý
- Runtime chỉ truy xuất các retrieval unit của revision `published`, đã duyệt, document `active` và retrieval unit `active`.
- Intent `comparison_history` dung path rieng `mode=\"historical\"`; metadata di ra `historical_references` va khong duoc tron vao `provision_citations`.
- `effective_status` cho van ban khong con active co the tra nhanh lifecycle voi trang thai, ngay hieu luc, ngay het hieu luc va van ban thay the/annul neu da co quan he duoc duyet.
- Neu cau hoi neu nhieu moc ngay hoac van ban lich su co nhieu giai doan ma user chua chot moc nao, SSE `done` phai roi vao `answer_mode = clarification_needed`.
- Sau rerank, evidence policy deterministic co the chen prompt notice hoac short-circuit response:
  - query tong quat nhieu van ban bo sung nhau se giu `answer_mode=direct` nhung buoc model trinh bay vai tro `Luat -> Nghi dinh -> Thong tu`
  - query cu the ve muc phat uu tien van ban co can cu truc tiep cho con so xu phat, thuong la nghi dinh
  - near-tie khac huong se roi vao `clarification_needed`, `multiple_possibilities` hoac `insufficient_evidence` tuy nguyen nhan
- Legal advice boundary chay truoc retrieval:
  - cau hoi chien luoc ca nhan hoa nhu `Toi nen kien khong?`, `Lam sao de tranh bi phat?` se short-circuit voi `guardrail_reason = legal_advice_boundary`
  - metadata van tra `risk_level = high` va `answer_mode = multiple_possibilities`
  - cau hoi thu tuc kieu `Toi nen lam gi de dang ky/doi/cap lai...` van duoc phep di tiep nhu query `procedure`
  - answer cho `procedure` phai nghieng ve checklist khach quan: ho so, co quan tiep nhan, thoi han, trinh tu, dieu kien
- Trước retrieval, backend có follow-up resolver deterministic:
  - chỉ dùng `conversation_context` khi câu hiện tại là follow-up và history đủ rõ
  - nếu confidence thấp thì trả `clarification_needed`
  - history chỉ dùng để hiểu topic, không trở thành căn cứ pháp lý
- Khi người dùng hỏi theo số hiệu văn bản:
  - `document_lookup`, `effective_status`, `standard_summary` có fast-path theo văn bản đang công bố.
  - Nếu không tìm thấy đúng số hiệu trong kho hiện hành thì trả lời ngắn gọn, không fallback sang dữ liệu cũ.

---

## 4. Public documents

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `GET` | `/documents` | Public | Danh sách văn bản đang công bố |
| `GET` | `/documents/{document_id}` | Public | Chi tiết văn bản đang công bố |
| `GET` | `/documents/{document_id}/source` | Public | Tải/xem file nguồn của bản đang công bố |
| `GET` | `/documents/{document_id}/summary` | Public | Tóm tắt chuẩn đã duyệt |
| `POST` | `/documents/{document_id}/summary/dynamic` | Public | Tóm tắt động có citation/disclaimer |
| `GET` | `/documents/citations/{retrieval_unit_id}` | Public | Metadata trích dẫn lịch sử để giữ click-through |
| `GET` | `/documents/citations/{retrieval_unit_id}/source` | Public | File nguồn cho trích dẫn lịch sử |

### 4.1 `GET /documents`

- Chỉ trả các văn bản có revision mới nhất ở trạng thái `published` và `legal_status='active'`.
- Văn bản `suspended`, `expired`, `replaced` hoặc `annulled` chỉ được giữ cho quản trị/lịch sử; không nằm trong danh sách public hiện hành.
- Hỗ trợ tìm theo `title` và `document_number`.
- Mỗi item public hiện có các field UI đang dùng:
  - `doc_id`
  - `title`
  - `doc_type`
  - `status`
  - `document_number`
  - `issued_date`
  - `effective_date`
  - `expiry_date`
  - `issuer`
  - `source_url`
  - `source_file_name`
  - `source_download_url`
  - `viewer_warning`
  - `standard_summary_url`
  - `current_revision_id`
  - `relations`

`relations` là danh sách quan hệ văn bản đã được duyệt và đang được phép hiển thị cùng văn bản public. Mỗi item gồm `relation_id`, `relation_type`, `direction`, `source_locator`, `target_locator`, `counterpart_document_id`, `counterpart_title`, `counterpart_document_number` và `counterpart_legal_status`. API trả cả quan hệ đi và quan hệ đến để người dùng có bối cảnh đầy đủ, nhưng đây chỉ là dữ liệu đọc; public UI không có thao tác quản trị quan hệ.

### 4.2 Source viewer

- Public source và historical citation source luôn trả header `X-LegalAI-Viewer-Warning`.
- Local storage phải qua kiểm tra containment; object storage dùng URL công khai hoặc presigned URL.
- Không lộ đường dẫn nội bộ của file.

### 4.3 Historical citation

- Dùng để giữ khả năng mở lại nguồn của một citation đã từng xuất hiện trong câu trả lời.
- Có thể mở metadata/source của retrieval unit thuộc revision `published`, `suspended` hoặc `archived`.
- Đây là ngoại lệ phục vụ provenance; không có nghĩa văn bản ngoài `active` được đưa lại vào public list hay chatbot.

---

## 5. Notifications

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `GET` | `/notifications` | USER | Danh sách thông báo của chính người dùng |
| `GET` | `/notifications/unread-count` | USER | Số thông báo chưa đọc |
| `PATCH` | `/notifications/{notification_id}/read` | USER | Đánh dấu đã đọc |
| `PATCH` | `/notifications/read-all` | USER | Đánh dấu tất cả đã đọc |
| `GET` | `/notifications/stream` | USER | SSE thông báo realtime |

---

## 6. Quản trị kho văn bản

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `POST` | `/admin/kb-v2/revisions/upload` | ADMIN | Tải DOCX vào luồng duyệt |
| `GET` | `/admin/kb-v2/revisions` | ADMIN | Danh sách hồ sơ duyệt |
| `GET` | `/admin/kb-v2/revisions/{revision_id}` | ADMIN | Chi tiết hồ sơ duyệt |
| `GET` | `/admin/kb-v2/revisions/{revision_id}/source` | ADMIN | Tải file nguồn theo revision |
| `GET` | `/admin/kb-v2/documents` | ADMIN | Danh sách văn bản đã hoặc từng công bố |
| `GET` | `/admin/kb-v2/relation-targets` | ADMIN | Tìm văn bản đích để tạo quan hệ trên toàn bộ hồ sơ; hỗ trợ `q`, `exclude_document_id`, `limit` |
| `GET` | `/admin/kb-v2/documents/{document_id}` | ADMIN | Chi tiết văn bản trong Kho văn bản |
| `PATCH` | `/admin/kb-v2/documents/{document_id}` | ADMIN | Sửa metadata văn bản đã công bố |
| `POST` | `/admin/kb-v2/documents/{document_id}/status` | ADMIN | Đổi trạng thái quản trị |
| `POST` | `/admin/kb-v2/documents/{document_id}/replacement-revisions/upload` | ADMIN | Tạo hồ sơ thay file nguồn cho văn bản đang quản lý |
| `POST` | `/admin/kb-v2/revisions/{revision_id}/metadata-proposals` | ADMIN | Tạo đề xuất metadata |
| `POST` | `/admin/kb-v2/metadata-proposals/{proposal_id}/review` | ADMIN | Duyệt đề xuất metadata |
| `POST` | `/admin/kb-v2/nodes/{node_id}/review` | ADMIN | Duyệt một mục nội dung |
| `POST` | `/admin/kb-v2/nodes/{node_id}/reset-review` | ADMIN | Đưa mục nội dung về cần kiểm tra |
| `POST` | `/admin/kb-v2/revisions/{revision_id}/risky-nodes/bulk-review` | ADMIN | Duyệt nhanh nhóm mục cần xem kỹ |
| `POST` | `/admin/kb-v2/revisions/{revision_id}/relations` | ADMIN | Tạo quan hệ văn bản |
| `POST` | `/admin/kb-v2/relations/{relation_id}/review` | ADMIN | Duyệt quan hệ |
| `PATCH` | `/admin/kb-v2/relations/{relation_id}` | ADMIN | Sửa quan hệ |
| `DELETE` | `/admin/kb-v2/relations/{relation_id}` | ADMIN | Loại bỏ quan hệ và ghi lịch sử xử lý |
| `POST` | `/admin/kb-v2/summaries/{summary_id}/review` | ADMIN | Duyệt tóm tắt chuẩn |
| `POST` | `/admin/kb-v2/revisions/{revision_id}/publish` | ADMIN | Công bố revision |
| `POST` | `/admin/kb-v2/revisions/{revision_id}/suspend` | ADMIN | Tạm ngừng công bố |
| `POST` | `/admin/kb-v2/revisions/{revision_id}/unsuspend` | ADMIN | Khôi phục công bố |

`GET /admin/kb-v2/revisions/{revision_id}` trả thêm các trường tổng hợp phục vụ màn `Duyệt văn bản`:

- `pending_metadata`
- `pending_relations`
- `pending_risky_nodes`
- `resolved_risky_nodes`
- `resolved_risky_count`
- `risky_reference_only_count`
- `risky_answerable_count`
- `is_ready_to_publish`

`publish_blockers` và `is_ready_to_publish` cũng phản ánh gate nội dung dùng cho hỏi đáp: revision phải có ít nhất một mục nội dung đã duyệt và được đánh dấu dùng cho hỏi đáp. Các mục chỉ để đối chiếu hoặc `answerable=false` không được tính là nội dung có thể đưa vào chatbot.

`relations` chứa cả quan hệ đi và quan hệ đến để hiển thị bối cảnh đầy đủ. `pending_relations` và `pending_relations_count` chỉ tính quan hệ đi ra từ văn bản của revision hiện tại; quan hệ đi vào được duyệt tại văn bản nguồn. Khi tạo quan hệ, API trả `422` nếu văn bản đích trùng văn bản nguồn và `409` nếu đã tồn tại cùng bộ nguồn, đích và loại quan hệ.

`POST /admin/kb-v2/revisions/{revision_id}/publish` là thao tác idempotent. Nếu
revision đã `published`, API trả `200` cùng chi tiết hiện tại, không tạo lại
retrieval units và không ghi thêm audit event. `409` chỉ dùng khi hồ sơ chưa đủ
điều kiện công bố.

`GET /admin/kb-v2/relation-targets` tìm theo `document_id`, số hiệu hoặc tiêu đề trực tiếp trên `kb_v2_legal_documents`, không giới hạn ở revision đã công bố. Frontend truyền `exclude_document_id` để loại văn bản đang duyệt và truy vấn lại khi người dùng nhập, thay vì chỉ lọc cục bộ một trang danh sách.

`PATCH /relations/{relation_id}` đưa quan hệ về trạng thái cần xử lý trước khi duyệt lại. `DELETE /relations/{relation_id}` xóa quan hệ, ghi review event `deleted` với nguồn, đích và loại quan hệ; nếu hồ sơ nguồn còn là bản nháp thì trạng thái duyệt của hồ sơ chuyển về `in_review`.

Frontend ưu tiên các trường tổng hợp này để xác định việc còn cần xử lý, mục đã kiểm tra và trạng thái sẵn sàng đưa vào kho. Không suy diễn lại toàn bộ từ danh sách node thô nếu API đã trả dữ liệu tổng hợp.

`POST /admin/kb-v2/documents/{document_id}/replacement-revisions/upload` tạo revision `draft` mới trên cùng `document_id` của văn bản đang quản lý. Endpoint này không ghi đè file, node hoặc retrieval unit của revision đang công bố; public/chatbot vẫn dùng revision `published` hiện hành cho tới khi hồ sơ thay file được duyệt và publish. Metadata proposal của revision thay file chỉ được áp dụng lên document ở bước publish, không áp dụng ngay khi reviewer duyệt proposal. Khi publish revision thay file, các revision `published` hoặc `suspended` cũ cùng `document_id` chuyển sang `archived`, retrieval units cũ chuyển sang trạng thái lịch sử để không tham gia trả lời mới.

Trong modal `Thông tin văn bản` của màn `Duyệt văn bản`, frontend áp dụng rule lưu như sau:

- revision `draft`: chỉnh các field chính bằng cách tạo hoặc cập nhật metadata proposal rồi duyệt ngay proposal đó qua `POST /admin/kb-v2/revisions/{revision_id}/metadata-proposals` và `POST /admin/kb-v2/metadata-proposals/{proposal_id}/review`
- revision đã ở trong kho (`published`, `suspended`, `archived`): lưu trực tiếp qua `PATCH /admin/kb-v2/documents/{document_id}` để giữ một nguồn sự thật theo `document_id`
- action trạng thái kho (`publish`, `suspend`, `unsuspend`) chỉ xuất hiện trong modal chỉnh sửa, không lặp lại ở accordion xem nhanh của card danh sách

`GET /admin/kb-v2/revisions` hiện cũng trả đủ dữ liệu cho card hồ sơ ở màn `Duyệt văn bản`:

- `issuing_authority`
- `effective_date`
- `expiry_date`
- `pending_metadata_count`
- `pending_relations_count`
- `pending_risky_nodes_count`
- `summary_status`
- `publish_blockers_count`
- `is_ready_to_publish`
- `relation_count`

Card danh sách dùng các trường này để ưu tiên hiển thị “việc cần xử lý trước”: badge trạng thái, loại văn bản, số hiệu, số việc còn lại; dưới tiêu đề là cơ quan ban hành và ngày hiệu lực.

Metadata văn bản dùng bộ giá trị canonical sau để tránh lệch giữa `Duyệt văn bản`, `Kho văn bản`, public search và chatbot:

- `document_type`: `LUAT`, `BO_LUAT`, `NGHI_DINH`, `THONG_TU`, `QUYET_DINH`, `CONG_VAN`, `QCVN`, `UNKNOWN`. Giá trị cũ `QUY_CHUAN` chỉ là alias nội bộ và được chuẩn hóa về `QCVN`.
- `document_role`: `primary`, `amendment`, `replacement`, `guidance`, `foundation`, `reference`, `technical`. Các giá trị cũ như `base`, `original`, `amending`, `guiding` chỉ được chấp nhận như alias khi đọc dữ liệu cũ và không được dùng làm nhãn UI.
- `relation_type`: giữ đúng 6 loại `amends`, `supplements`, `replaces`, `annuls`, `guides`, `depends_on`. UI hiển thị `depends_on` là `Căn cứ liên quan` để tránh nhầm với vai trò văn bản.

Ngữ nghĩa thời gian của card hồ sơ:

- `uploaded_at`: mốc tạo hồ sơ
- `updated_at`: chỉ có giá trị khi hồ sơ đã có review event thực sự sau bước tạo; event `created` không được tính là cập nhật cuối
- nếu `updated_at` là `null`, frontend phải hiển thị theo nhãn `Tạo hồ sơ` thay vì giả lập thành `Cập nhật gần nhất`
- nếu list hồ sơ gặp lỗi nội bộ ngoài nhóm database, API phải trả `500` với `detail.code = KB_DOCUMENT_LIST_UNAVAILABLE` và thông điệp tiếng Việt
- nếu mở chi tiết hồ sơ gặp lỗi nội bộ ngoài nhóm database, API phải trả `500` với `detail.code = KB_REVISION_DETAIL_UNAVAILABLE` và thông điệp tiếng Việt

### 6.1 `GET /admin/kb-v2/documents`

- Trả danh sách văn bản đã hoặc từng công bố cho màn `Kho văn bản`.
- Không được trả danh sách rỗng để né lỗi.
- Response phải giữ các field UI đang dùng:
  - `document_id`
  - `revision_id`
  - `title`
  - `document_number`
  - `document_type`
  - `issuing_authority`
  - `effective_date`
  - `expiry_date`
  - `legal_status`
  - `publication_status`
  - `display_status`
  - `source_file_name`
  - `updated_at`
  - `relation_count`
- Serialization phải eager-load các quan hệ cần thiết để tránh lỗi async lazy-load kiểu `MissingGreenlet`.

### 6.2 Trạng thái quản trị

- `active`: đang công bố và được dùng cho public/chat.
- `suspended`: tạm ngừng công bố, ẩn khỏi public/chat.
- `expired`, `replaced`, `annulled`: trạng thái vòng đời lịch sử để admin theo dõi; không hiển thị trong public list hiện hành và không được chatbot dùng cho câu trả lời mới.

---

## 7. Quản trị tài sản biển báo

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `GET` | `/admin/traffic-sign-assets/review` | ADMIN | Danh sách asset cần rà |
| `PATCH` | `/admin/traffic-sign-assets/{asset_id}` | ADMIN | Cập nhật asset |

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `GET` | `/traffic-signs` | Public | Danh sách biển báo đã duyệt |
| `GET` | `/traffic-signs/{sign_code}` | Public | Chi tiết biển báo |
| `GET` | `/assets/{asset_id}` | Public | Tải asset đã duyệt |

---

## 8. Chất lượng AI

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `GET` | `/admin/quality/overview` | ADMIN | Tổng quan sức khỏe chatbot |
| `GET` | `/admin/quality/issues` | ADMIN | Danh sách vấn đề |
| `GET` | `/admin/quality/issues/{issue_id}` | ADMIN | Chi tiết một vấn đề |
| `POST` | `/admin/quality/issues/{issue_id}/review` | ADMIN | Ghi kết luận rà soát |
| `GET` | `/admin/quality/release-checks` | ADMIN | Danh sách lần kiểm chuẩn |
| `GET` | `/admin/quality/release-checks/{run_id}` | ADMIN | Chi tiết một lần kiểm chuẩn |

---

## 9. Quản trị người dùng

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `GET` | `/admin/users` | ADMIN | Danh sách người dùng |
| `GET` | `/admin/users/export` | ADMIN | Xuất danh sách người dùng |
| `POST` | `/admin/users` | ADMIN | Tạo người dùng |
| `PATCH` | `/admin/users/{user_id}` | ADMIN | Cập nhật người dùng |
| `POST` | `/admin/users/{user_id}/reset-password` | ADMIN | Đặt lại mật khẩu |
| `DELETE` | `/admin/users/{user_id}` | ADMIN | Khóa mềm tài khoản |

---

## 10. Health

| Method | Endpoint | Quyền | Mục đích |
|---|---|---|---|
| `GET` | `/health` | Public | Healthcheck của backend |

`/health` hiện trả các trường:

- `status`
- `env`
- `commit`
- `admin_quality_route`

---

## 11. Mã lỗi vận hành cần lưu ý

| HTTP | Code | Ý nghĩa |
|---|---|---|
| `401` | `UNAUTHORIZED` | Thiếu hoặc sai JWT |
| `403` | `FORBIDDEN` | Không đủ quyền |
| `404` | `NOT_FOUND` | Không tìm thấy tài nguyên |
| `500` | `KB_DOCUMENT_LIST_UNAVAILABLE` | Không tải được danh sách Kho văn bản |
| `503` | `KB_DATABASE_UNAVAILABLE` | PostgreSQL chưa sẵn sàng |
| `503` | `KB_SCHEMA_NOT_READY` | Chưa chạy migration tới schema mới |
| `503` | `KB_DATABASE_ERROR` | Database lỗi khi xử lý Kho văn bản |

Tài liệu này mô tả contract vận hành hiện tại. Không dùng placeholder cutover cũ và không coi dữ liệu `legal_documents`/`document_chunks` là nguồn runtime cho public/chat nữa.
### Ghi chú API cho form `Thông tin văn bản`

- `PATCH /admin/kb-v2/revisions/{revision_id}/source` cập nhật metadata nguồn của revision, gồm `source_url`, `source_downloaded_at`, `source_note` và `source_file_name`.
- Trong màn `Duyệt văn bản`, form `Thông tin văn bản` lưu tóm tắt chuẩn qua `POST /admin/kb-v2/summaries/{summary_id}/review`.
- Với revision `draft`, metadata pháp lý vẫn đi qua metadata proposal; metadata nguồn đi qua endpoint revision source để không trộn dữ liệu file nguồn vào proposal pháp lý.

### 3.2 Runtime contract locked by golden eval

Golden eval hien tai da co case khoa truc tiep cho cac branch `/chat/stream` sau:

- `direct` + `provision_citations`
- `summary` + `document_sources`
- `historical` + `historical_references`
- follow-up resolved tu `conversation_context`
- `clarification_needed` + `clarification_question`
- `multiple_possibilities` cho near-tie va `legal_advice_boundary`
- `out_of_scope` cho prompt injection yeu cau bo citation/disclaimer
