# Kế hoạch hoàn thiện VTLaw

**Ngày lập:** 07/11/2026
**Trạng thái:** Kế hoạch thực hiện, chưa phải xác nhận đã đạt release gate
**Mục tiêu:** Phát hành pilot tra cứu pháp luật giao thông có phạm vi rõ, dữ liệu có provenance, câu trả lời kiểm chứng được và quy trình sửa lỗi không làm mất dữ liệu hay bỏ qua duyệt.

Phạm vi và hành vi sản phẩm tuân theo bộ tài liệu chuẩn hiện hành trong `docs/project/`; kế hoạch này tổ chức công việc thực hiện, không thay thế các đặc tả đó.

## 1. Nguyên tắc phát hành

1. Chỉ mở các chủ đề mà corpus đã được kiểm kê, đối chiếu nguồn và duyệt. Không tuyên bố corpus đầy đủ chỉ vì đã nhập hết các tệp đang có.
2. Giữ phạm vi người đi bộ, xe đạp/xe đạp điện, xe máy, người lái và chủ ô tô cá nhân. Không tự mở rộng sang SME, đội xe, nghiệp vụ doanh nghiệp vận tải, OCR hay hiểu ảnh.
3. Chỉ revision đã review, publish và còn hiệu lực mới được dùng làm căn cứ hiện hành. Eligibility phải được áp dụng trước dense/vector search.
4. Mỗi khẳng định pháp lý có citation hợp lệ hoặc được thay bằng câu trả lời thiếu căn cứ; mọi đầu ra pháp lý có disclaimer.
5. Parser thành công không đồng nghĩa nội dung đúng luật, đầy đủ hay answerable. Publish cần người có thẩm quyền xác nhận.
6. Không sửa đè tệp gốc hoặc revision đang phục vụ. Sửa nguồn tạo revision/rendition mới, giữ checksum và provenance.
7. Không có trạng thái “cần kiểm duyệt” nào là ngõ cụt: mỗi issue phải chỉ rõ nguyên nhân có thể có, hành động sửa, cách chạy lại, cách xác minh và cách vô hiệu hóa an toàn.

## 2. Tình trạng nền đã kiểm tra

### Đã có trong codebase

- Next.js frontend, FastAPI API, LangGraph, PostgreSQL/pgvector, Alembic và cấu hình object storage S3-compatible.
- Luồng KB có upload, checksum, revision, canonical nodes, review, publish, suspend và retrieval units.
- Retrieval hybrid, metadata thời gian, citation verification, guardrail và response metadata.
- Admin UI cho kho/duyệt văn bản, chất lượng AI và user; có unit/API/RAG tests cùng golden dataset.

### Khoảng trống cần biến thành release work

- KB upload hiện chỉ nhận DOCX. DOCX parser duyệt paragraph/table trong body, flatten bảng thành dòng văn bản; chưa có bằng chứng về kiểm kê mọi OOXML part, hidden text, comments, tracked changes, headers/footers, footnotes/endnotes hay embedded objects.
- Parse warning hiện chưa tạo được một quy trình sửa chữa theo mã lỗi có bước chạy lại và xác minh xuyên suốt.
- Corpus chưa được xác nhận đủ hoặc thẩm định hiệu lực. Snapshot kiểm kê cũ không thay thế inventory hiện hành; manifest phải được đối soát với nguồn chính thức trước pilot.
- Kiểm tra tại Windows ngày lập: frontend lint đạt. Ruff xác nhận 17 lỗi (16 lỗi sắp xếp import và một import sau bootstrap `sys.path`). Pytest chạy tới hết nhưng có lỗi quyền ghi/duyệt temp directory ở môi trường Windows sandbox; không xem đó là test pass sạch. Frontend build bị `EPERM` khi ghi `.next/trace-build`. Các lỗi quyền này cần được xác minh trên runner Linux; không dùng chúng để che test failure thực sự.
- Golden dataset hiện có 7 tệp, khoảng 145 dòng case; full evaluation chưa được xác nhận đã chạy đạt.

## 3. Thứ tự triển khai và cổng hoàn thành

### Giai đoạn 0 — Khóa pilot và tiêu chí chấp nhận

- Đã khóa trong `docs/project/01-product-scope-and-corpus.md`: persona cá nhân hỏi về hành vi vi phạm, khung phạt và điểm giấy phép; chủ đề hỗ trợ/ngoài phạm vi; điều kiện hỏi lại và điều kiện tắt khi thiếu nguồn.
- Nguồn bắt buộc là văn bản chính thức điều chỉnh hành vi và chế tài; chủ đề điểm cần căn cứ trực tiếp về điểm. Đối chiếu hiệu lực, sửa đổi/thay thế theo điều khoản và ngày xảy ra. Không mở rộng sang QCVN 41 hoặc Thông tư 51/2024/TT-BGTVT/tệp QCVN.
- Chủ dự án chịu trách nhiệm quyết định phạm vi, chấp nhận nguồn vào corpus và quyết định phát hành. Đây không phải xác nhận chuyên môn pháp lý; Codex không chứng nhận hiệu lực/diễn giải luật. Chủ đề chỉ được bật sau khi corpus tương ứng qua inventory/review ở Giai đoạn 2.

**Cổng qua:** Phạm vi và người ra quyết định đã được ghi nhận; thiếu nguồn đồng nghĩa chủ đề tắt, không trì hoãn bằng cách mở rộng yêu cầu tải thêm văn bản ngoài pilot. Giai đoạn 0 hoàn tất; điều kiện nguồn để bật chủ đề là gate ở Giai đoạn 2.

### Giai đoạn 1 — Làm xanh môi trường và CI

- Sửa và chạy Ruff cho `src/` và `tests/`; dùng pytest trên runner Linux, không coi lỗi setup/temp là pass.
- Chạy toàn bộ backend test offline và test PostgreSQL thiết yếu sau migration từ database rỗng dùng pgvector. CI không cung cấp OpenAI secret; các test đòi provider thật không chạy trên mỗi PR.
- Chạy frontend lint và production build trên Linux.
- Không bắt buộc Playwright trên mọi PR: các spec hiện tại cần backend, dữ liệu đã seed và thông tin đăng nhập admin, nên không phải smoke test độc lập. Chạy E2E trên môi trường staging/release sau khi đã có fixture và credentials chuyên dụng; lưu trace/artifact khi lỗi.
- Full RAG evaluation có OpenAI thật chỉ chạy thủ công/có kiểm soát chi phí trước release, không nằm trong CI thường trực.

**Cổng qua:** Required PR jobs chạy xanh từ runner sạch; không có test lỗi/skip bị che; migration từ DB rỗng và test truy vấn PostgreSQL thiết yếu chạy thật; frontend lint/build thành công. E2E và full eval được giữ ở release gates có môi trường phù hợp.

**Trạng thái kiểm chứng ngày 07/11/2026:** workflow CI gồm job backend (Ruff, PostgreSQL/pgvector 0.8.0, Alembic từ DB sạch, pytest) và job frontend (lint, production build); không dùng API key thật. Đã sửa 17 lỗi Ruff, thêm regression active-filter trước vector ranking và sửa cú pháp eval tương thích Python 3.11 sau khi runner phát hiện lỗi thu thập test. Ngoài sandbox, Alembic migrate DB rỗng thành công; full pytest với PostgreSQL chạy **579 passed, 0 skipped, 0 failed**; `ruff check` pass; frontend lint và `next build` (gồm TypeScript/static generation) pass; Playwright Chromium chạy chat clarification trên production build với API mock, **1/1 pass**. Workflow GitHub Actions của PR #1 chạy trên runner sạch ngày 07/11/2026: backend và frontend đều **SUCCESS**. Test temp mặc định của Windows bị sandbox chặn; dùng basetemp ghi được cho các lượt kiểm tra cục bộ. Hai cảnh báo backend hiện có là Starlette/httpx deprecation và asyncio connection-cancel warning, không làm fail suite.

**Trạng thái cổng:** Giai đoạn 1 hoàn tất; migration DB rỗng, backend tests, Ruff, frontend lint/build đã được xác minh cục bộ và trên GitHub-hosted runner. PR #1 còn mở, chưa merge; các commit và checks được giữ để review. CI không cần đưa full RAG eval hoặc bộ E2E phụ thuộc corpus/admin vào mỗi PR.

### Giai đoạn 2 — Corpus inventory và provenance

- Xem `data/` là thư mục đầu vào các văn bản nguồn do chủ dự án cung cấp, độc lập với `corpus/`. Một tệp vẫn là nguồn cần kiểm tra nếu trước đây được tải từ hoặc sao chép qua `corpus/`; không loại hay phân loại lại chỉ vì provenance cũ. Không tự sửa, xóa, tải thay thế hoặc đưa thêm văn bản vào `data/`.
- Khi rà soát `data/`, báo riêng cho chủ dự án lỗi tệp/parse và văn bản còn thiếu nhưng thực sự cần cho scope đã chốt. Với mỗi thiếu hụt, nêu chủ đề/câu hỏi bị ảnh hưởng, văn bản và căn cứ chính thức xác định nhu cầu, cùng lựa chọn bổ sung hoặc thu hẹp câu hỏi; chờ chủ dự án xác nhận trước khi thêm nguồn.
- Tạo manifest có version thay cho checklist thủ công đơn lẻ. Mỗi nguồn gồm: document number, title, issuing authority, official URL, ngày tải, checksum SHA-256, loại file, ngày ban hành/hiệu lực/hết hiệu lực, văn bản sửa đổi/thay thế/bãi bỏ, tình trạng bản gốc và người xác nhận.
- Đối chiếu từng file với nguồn chính thức; không dùng tên file, metadata do mô hình đoán hoặc một cờ status cấp văn bản làm bằng chứng đủ.
- Kiểm tra đủ trang, phần, phụ lục, biểu mẫu, bảng và ghi chú; lập mapping giữa nội dung hợp nhất và văn bản sửa đổi theo điều khoản/thời điểm.
- Tạo coverage matrix `chủ đề/câu hỏi -> văn bản -> điều khoản -> thời điểm -> trạng thái review`.
- Ghi lý do cho từng nguồn ngoài phạm vi, thiếu, trùng, không rõ nguồn hoặc chỉ dùng tham khảo.

**Cổng qua:** Mọi đơn vị corpus pilot truy được tới nguồn và checksum; các khoảng trống được đánh dấu không answerable, không bị lấp bằng suy luận.

### Giai đoạn 3 — Hợp đồng parse DOCX và kiểm kê package

Trước khi cải thiện parser, tạo bộ DOCX fixture đại diện và đặc tả rõ mỗi package part được trích xuất, đưa review-only, bỏ có lý do hay chặn publish. Mọi entry trong ZIP package phải được phân loại; part chưa biết không được âm thầm bỏ.

| Thành phần | Phát hiện và cách xử lý dự kiến |
|---|---|
| `word/document.xml`: paragraph, heading, body text | Giữ thứ tự nguồn, style/heading, run, page/section break khi có thể; lưu locator tới part và thứ tự block. |
| Bảng, bảng lồng, ô gộp, hàng lặp tiêu đề | Giữ cấu trúc hàng/cột và cell tọa độ; không chỉ nối chuỗi bằng `|` nếu làm mất quan hệ cột. Bảng có mức phạt/điều kiện phải qua review trước khi answerable. |
| `numbering.xml`, danh sách đánh số/bullet | Giải số thứ tự từ `numId/ilvl`, kế thừa style; phân biệt số Khoản/Điểm pháp lý với list trình bày. Mơ hồ thì phát issue và block answerability. |
| `header*.xml`, `footer*.xml` | Kiểm kê theo section/relationship; loại header/footer lặp chỉ khi chứng minh là phần trang trí; nội dung quy phạm không được loại chỉ vì nằm ngoài body. |
| Footnotes/endnotes | Trích và nối đúng marker với nội dung; nếu parser chưa hỗ trợ thì review-only/block, không bỏ qua vì không nằm trong `document.xml`. |
| Comments/annotation | Không coi comment của người soạn là luật; phát hiện, lưu trạng thái review-only và cảnh báo để người duyệt xác nhận không chứa nội dung cần thiết. |
| Tracked changes: insert/delete/move | Phát hiện mọi revision markup. Không nhập đồng thời cả bản cũ và bản sửa; mặc định chặn publish đến khi người duyệt chọn bản có căn cứ hoặc cung cấp nguồn clean đã đối chiếu. |
| Hidden text: `w:vanish`, `w:webHidden`, run bị ẩn | Đếm, định vị và hiển thị cảnh báo riêng; không âm thầm xóa hoặc tự đưa vào evidence. Người duyệt quyết định đối chiếu/loại/đưa vào rendition đã xác minh. |
| Hyperlink, field, external relationship | Giữ visible text và URL như provenance khi an toàn; tuyệt đối không tự tải URL ngoài. Field kết quả và field code phải phân biệt khi có khả năng khác nội dung. |
| Drawing, chart, SmartArt, text box, equation | Kiểm kê relationship và nội dung; nếu chưa có adapter đầy đủ thì gắn `visual_or_embedded_content_unparsed`, review-only và không cho câu trả lời phụ thuộc phần đó. |
| Ảnh, scan, OLE/embedded package, `altChunk` | Chỉ lưu tham chiếu/hash và trạng thái. Không chạy macro, không thực thi/đọc file nhúng không tin cậy. OCR/vision không thuộc pilot; cần bản văn bản được con người đối chiếu hoặc đánh dấu không answerable. |
| XML/package parts không nhận diện | Lưu tên part/content type/relationship, loại `unsupported_part`; yêu cầu kỹ thuật phân loại. Không cho “parser confidence cao” che khuất part chưa hỗ trợ. |
| File ẩn trên filesystem: `~$*.docx`, `.DS_Store`, `Thumbs.db`, hidden/system, file tạm | Không đưa vào ingest. Đưa vào inventory quarantine với lý do `non_corpus_artifact`; cho phép admin bỏ khỏi batch hoặc chọn đúng file nguồn. |
| File không phải DOCX, DOCX mã hóa/hỏng, MIME giả, ZIP bất thường | Kiểm tra extension + magic/ZIP/OOXML; giới hạn kích thước, số entry, kích thước giải nén và tỷ lệ nén. Từ chối/quarantine có mã lỗi, không treo request hay để parser đọc nội dung tùy ý. |

### Giai đoạn 4 — Parse report, issue registry và UI sửa lỗi

Mỗi lần parse cần một report bất biến gắn với `revision_id`, source SHA-256, parser/version, thời điểm chạy và attempt. Report tối thiểu ghi:

- Danh sách package parts: `extracted`, `review_only`, `ignored_with_reason`, `unsupported`, `failed`.
- Số paragraph/table/row/cell/heading/hidden run/tracked change/comment/media/relationship theo part.
- Block đã trích xuất cùng thứ tự, locator, node cha, checksum nội dung và trạng thái answerability.
- Cảnh báo có mã ổn định, mức độ, vị trí nguồn, mô tả dễ hiểu, ảnh hưởng, cách xử lý và điều kiện publish.
- Parser confidence theo block/part; confidence tài liệu không được che lấp một vùng critical bị mất.

Nếu review history hiện tại không đủ biểu diễn từng lỗi và cách giải quyết, bổ sung bảng issue liên kết revision thay vì chỉ nhét chuỗi warning vào JSON. Một issue có tối thiểu: `issue_code`, severity, package part/locator, source hash, parser version, trạng thái, resolution type/note, actor, timestamps và attempt đã xác minh.

Trạng thái issue đề xuất: `open -> triaged -> action_required -> fixing -> verification_required -> resolved`; nhánh kết thúc an toàn gồm `excluded_non_answerable` hoặc `accepted_review_only` với lý do/người duyệt. Không có thao tác “dismiss” làm biến mất audit.

#### Hợp đồng ngôn ngữ cho giao diện kiểm duyệt

- Mọi tiêu đề, mô tả lỗi, mức ảnh hưởng, hành động, trạng thái và thông báo fallback mà kiểm duyệt viên nhìn thấy phải là tiếng Việt có dấu, UTF-8, câu ngắn và dễ hiểu. Không hiển thị lỗi tiếng Anh thô, stack trace, raw UUID, tên bảng, tên class, tên part XML hoặc thuật ngữ nội bộ nếu chưa giải thích.
- Mỗi lỗi trình bày theo cùng thứ tự: **Đã xảy ra việc gì?** -> **Ảnh hưởng gì?** -> **Có thể tiếp tục dùng để trả lời không?** -> **Bạn có thể làm gì tiếp theo?** -> **Cách biết đã xử lý xong.** Nội dung phải nêu rõ phần nào của văn bản/câu trả lời bị ảnh hưởng.
- Chỉ đưa hành động phù hợp vai trò: kiểm duyệt viên có thể mở vị trí nguồn, xem đối chiếu, quyết định “Chỉ dùng để tham khảo”/“Không dùng để trả lời” khi được phép, tải báo cáo hoặc gửi lỗi kỹ thuật; không yêu cầu họ sửa code, JSON, SQL hay tự đoán nguyên nhân.
- Giữ mã lỗi, parser/model version, part/locator, checksum và trace ID trong khu **Chi tiết kỹ thuật** thu gọn, có nút sao chép để Codex/dev dùng chẩn đoán. Mã nội bộ không thay cho bản giải thích tiếng Việt và không phải hành động duy nhất.
- Từ điển lỗi tiếng Việt là nguồn dùng chung cho API/UI; mỗi mã có `title_vi`, `explanation_vi`, `impact_vi`, `safe_actions_vi` và `resolution_check_vi`. Unknown code vẫn có fallback tiếng Việt kèm mã/trace để gửi hỗ trợ.
- Kiểm thử giao diện bắt buộc xác nhận dấu tiếng Việt không lỗi font/mojibake, text không tràn mobile, không lộ stack/secret và mọi nút xử lý có kết quả/empty/error state rõ ràng.

Ví dụ cho reviewer: **“Chưa đọc được nội dung trong một bảng ở Điều 12. Bảng này chưa được dùng để trả lời. Bạn có thể mở vị trí nguồn để đối chiếu, đánh dấu chỉ tham khảo, hoặc gửi chi tiết kỹ thuật cho nhóm phát triển. Sau khi sửa, hãy chạy lại bước phân tích và xác nhận nội dung bảng trước khi đưa văn bản vào kho.”**

Catalog mã lỗi ban đầu cần được version hóa và dùng chung giữa parser/API/UI/log/eval:

| Mã | Phát hiện | Hành động mặc định |
|---|---|---|
| `KB_UPLOAD_NON_CORPUS_ARTIFACT` | File tạm/ẩn hoặc không phải nguồn được chọn | Loại khỏi batch hoặc chọn file đúng; không parse. |
| `KB_UPLOAD_TYPE_MISMATCH` | Extension, MIME và magic bytes không khớp | Quarantine; yêu cầu nguồn đúng định dạng. |
| `KB_DOCX_ENCRYPTED` | DOCX mã hóa hoặc không đọc được | Yêu cầu bản DOCX chính thức không mã hóa; không tự phá mật khẩu. |
| `KB_DOCX_PACKAGE_INVALID` | ZIP/OOXML hỏng hoặc thiếu relationship/content type | Giữ source/hash; yêu cầu tải lại hoặc revision nguồn khác. |
| `KB_DOCX_PACKAGE_LIMIT_EXCEEDED` | Vượt giới hạn entry/giải nén/tỷ lệ nén | Từ chối an toàn; operator xem xét ngoài luồng, không tăng giới hạn tùy tiện. |
| `KB_OOXML_PART_UNSUPPORTED` | Có package part chưa được phân loại | Chặn publish; kỹ thuật thêm adapter hoặc reviewer loại phần khỏi answerability có lý do. |
| `KB_DOCX_HIDDEN_TEXT_PRESENT` | Run có cờ hidden/vanish hoặc hidden content khác | Review-only mặc định; đối chiếu nguồn và ghi quyết định. |
| `KB_DOCX_TRACKED_CHANGES_PRESENT` | Insert/delete/move chưa được chấp nhận | Chặn publish đến khi chọn bản có căn cứ hoặc dùng nguồn clean đã xác minh. |
| `KB_DOCX_COMMENT_PRESENT` | Có comments/annotation | Review-only; xác nhận không chứa nội dung quy phạm cần thiết. |
| `KB_DOCX_VISUAL_CONTENT_UNPARSED` | Ảnh, chart, SmartArt, text box, equation hoặc OLE chưa xử lý | Không trả lời dựa vào phần đó; cung cấp rendition đã xác minh hoặc loại rõ ràng. |
| `KB_DOCX_TABLE_STRUCTURE_UNCERTAIN` | Mất header/cell/merge/đơn vị/liên hệ chú thích | Review-only; sửa adapter/rendition, đối chiếu bảng trước publish. |
| `KB_DOCX_NUMBERING_AMBIGUOUS` | Không phân biệt được list trình bày với Khoản/Điểm | Chặn node; sửa mapping/parser và regression. |
| `KB_DOCX_NOTE_UNMAPPED` | Footnote/endnote không nối được marker hoặc locator | Review-only; nối lại bằng parser hoặc rendition có mapping. |
| `KB_PARSE_NO_TEXT` | Không có text/block answerable sau extraction | Không publish; kiểm tra scan/ảnh/encryption/format, dùng nguồn khác hoặc bản chuyển đổi được xác minh. |
| `KB_PARSE_STRUCTURE_MISMATCH` | Thiếu/trùng/sai thứ tự node hoặc locator | Chặn revision; xem diff cây parse, sửa adapter/mapping, review lại phần ảnh hưởng. |
| `KB_SOURCE_DUPLICATE` | SHA-256 đã tồn tại | Mở revision cũ để tiếp tục review; chỉ tạo revision mới khi nội dung nguồn thật sự khác. |
| `KB_PARSE_RETRYABLE_FAILURE` | Lỗi hạ tầng tạm trong lưu/trích xuất | Retry cùng hash/version có giới hạn; không tạo thêm revision/node trùng. |
| `KB_SOURCE_STORAGE_UNAVAILABLE` | Không đọc/ghi được file nguồn/object | Giữ publish state; retry sau khi storage khỏe, kiểm URI/checksum. |
| `KB_DATABASE_UNAVAILABLE` | DB/migration/schema chưa sẵn sàng | Không parse/publish một phần; kiểm health/migration rồi chạy lại an toàn. |
| `RAG_ACTIVE_FILTER_VIOLATION` | Candidate không đủ điều kiện lọt vào retrieval | Severity critical; dừng release/disable affected path, sửa filter trước vector search, regression bắt buộc. |
| `RAG_NO_EVIDENCE` | Không có evidence đủ điều kiện | Abstain/hỏi làm rõ; kiểm coverage/metadata/retrieval, không nới eligibility để ép có câu trả lời. |
| `RAG_CITATION_INVALID` | Sai source, revision, locator hoặc thời điểm | Chặn câu trả lời; sửa source mapping/retrieval unit, kiểm click-through. |
| `RAG_UNSUPPORTED_CLAIM` | Claim không được evidence hỗ trợ | Chặn output; lưu evidence IDs, sửa generation/verifier hoặc abstain; thêm golden case. |
| `RAG_DISCLAIMER_MISSING` | Nhánh pháp lý thiếu disclaimer | Severity critical; chặn release, sửa mọi đường response gồm SSE/deflect/history. |
| `RAG_TEMPORAL_CONFLICT` | Căn cứ không đúng ngày hỏi hoặc xung đột phiên bản | Hỏi lại/abstain; sửa provision validity và test mốc thời gian. |
| `RAG_NEAR_TIE_UNRESOLVED` | Evidence khác hướng/thiếu fact phân biệt | Hỏi clarification hoặc multiple possibilities; không để model tự chọn. |
| `CHAT_PROVIDER_TIMEOUT` | LLM/embedding/provider timeout hoặc quota | Báo dịch vụ gián đoạn với trace ID; retry có giới hạn, không giả dạng câu trả lời pháp lý. |
| `CHAT_STREAM_INTERRUPTED` | SSE đóng giữa chừng/không có terminal event | Client cho retry có kiểm soát; backend ghi trạng thái không hoàn tất, không lưu câu trả lời thiếu như hoàn chỉnh. |

Mỗi mã phải có metadata machine-readable tối thiểu: `severity`, `user_message`, `operator_action`, `can_publish`, `can_answer`, `retry_policy`, `runbook_ref` và `close_evidence`. Thêm mã mới phải có handler/UI fallback và test; mã lạ luôn fail closed, hiển thị trace ID và hướng liên hệ admin.

Mỗi issue trên UI phải trả lời được: chuyện gì xảy ra, nội dung nào bị ảnh hưởng, hiện có thể dùng để trả lời không, người duyệt có thể làm gì ngay, việc nào cần developer, cách chạy lại và tiêu chí đóng issue. Có nút mở đúng vị trí trong văn bản, tải nguồn/báo cáo và sao chép mã issue/trace trong phần kỹ thuật. Không dùng cảnh báo chỉ đọc mà không có hành động.

**Cổng qua:** Không còn warning chung chung kiểu “parser có thể sai” mà không có vị trí hoặc hành động; unresolved critical issue chặn publish.

### Giai đoạn 5 — Runbook khắc phục parse và KB

| Nhóm lỗi | Hành động phục hồi | Xác minh trước khi đóng |
|---|---|---|
| Upload hỏng/ZIP/OOXML không hợp lệ | Giữ file quarantine + checksum; thử lại chỉ khi lỗi storage/transport; nếu nguồn hỏng, tải bản chính thức khác thành source/revision mới. | Hash, package inventory, mở được source; không có partial revision được publish. |
| DOCX rỗng/không có text | Kiểm tra document.xml, ảnh/scan, encryption và format thực; yêu cầu DOCX nguồn khác hoặc bản chuyển đổi được kiểm chứng. | So số trang/phần và sample nội dung với nguồn; nếu chưa xác minh thì toàn revision không answerable. |
| Thiếu part, hidden text, comments, tracked changes | Tạo issue theo part/locator; người duyệt chọn `review-only`, loại khỏi answer hoặc cung cấp rendition sạch có mapping về file gốc; developer bổ sung parser khi lỗi mang tính hệ thống. | Part inventory không còn `unknown`; so sánh block count/nội dung trước-sau; review affected nodes lại. |
| Sai hierarchy Điều/Khoản/Điểm/list | Hiển thị cây parse và source order; cho phép sửa mapping/locator có audit hoặc nộp nguồn chuẩn hóa; sửa parser bằng fixture tái hiện. | Test cấu trúc và locator; kiểm tra parent-child, thứ tự, không duplicate/missing provision; build lại retrieval units ở draft. |
| Bảng/biểu mẫu/footnote/phụ lục bị flatten hoặc sai liên kết | Chuyển node thành review-only; sửa adapter/representation hoặc nhập rendition có kiểm chứng. Không duyệt bảng vì “đọc được text” nếu mất header/đơn vị/điều kiện. | Đối chiếu cell/header/footnote với nguồn; ca hỏi trên bảng phải trả đúng citation hoặc abstain. |
| Sai/thiếu metadata, ngày hiệu lực, quan hệ sửa đổi | Người có thẩm quyền sửa metadata proposal và relation tại hồ sơ; nếu nguồn khác thì tạo revision mới. | So nguồn chính thức; kiểm tra temporal query ở trước/trong/sau mốc hiệu lực. |
| Trùng nguồn/checksum | Mở revision đã có để review/tiếp tục; không tạo bản đang active trùng. Nếu khác nội dung dù tên giống, so checksum và provenance, không override. | Idempotency test, một nguồn gốc, audit event rõ. |
| Embedding/provider/database lỗi | Retry có giới hạn và backoff cho lỗi tạm; giữ trạng thái `retryable`; không lặp ingest hoặc tạo revision mới. Lỗi cấu hình hiển thị hướng dẫn operator, không trả stack trace. | Retry cùng source/parser version; số node/retrieval unit không tăng trùng; healthcheck provider/DB pass. |
| Parser mới làm thay đổi node | Reparse vào attempt/draft mới; giữ source và output cũ. Không giữ quyết định review nếu node identity/content hash đã đổi mà không đánh dấu stale. | Diff node cũ/mới theo locator/hash; reviewer xác nhận phần thay đổi; chạy regression fixture. |

**Quy tắc retry/reparse:** Retry cùng input chỉ dành cho lỗi hạ tầng/tạm thời; reparse dùng parser version mới; sửa nguồn luôn tạo revision hoặc rendition mới. Cả ba phải idempotent, lưu số attempt và không ghi đè kết quả đã publish.

### Giai đoạn 6 — Khép kín lỗi trả lời pháp lý

Mỗi báo cáo câu trả lời sai tạo quality issue có thể truy lại bằng `request_id/trace_id`, thời điểm hỏi, answer mode/risk, prompt/model/query-policy version, corpus snapshot, revision, retrieval-unit IDs, locator, ranking signals, verifier results và trạng thái disclaimer. Không lưu API key/token; nội dung query/source chỉ lưu khi chính sách dữ liệu cho phép, ưu tiên dữ liệu đã khử nhận dạng.

Phân loại root cause và hướng sửa bắt buộc:

| Root cause | Cách xử lý |
|---|---|
| Corpus/hiệu lực/quan hệ văn bản sai | Tạm dừng chủ đề/revision liên quan nếu gây rủi ro; người duyệt cập nhật nguồn/metadata/relation; re-review và chạy temporal tests. |
| Parser bỏ/sai nội dung | Mở parse issue liên kết citation locator; sửa adapter/rendition; reparse draft, kiểm tra diff, tạo test fixture; không vá riêng câu trả lời. |
| Retrieval bỏ sót hoặc chọn sai | Lưu candidate set; sửa exact/FTS/vector/ranker/query policy; thêm case có nhãn độc lập; so metric trước/sau. |
| Eligibility/active filter sai | Chặn release; khắc phục query để filter trước vector search; regression test xác nhận SQL/query plan và nguồn bị loại. |
| Generation claim không được evidence hỗ trợ | Chặn output bằng verifier/abstention; sửa context packing/prompt/verifier; thêm case phủ định, chủ thể, điều kiện, ngoại lệ và số liệu. |
| Citation sai locator/source/temporal | Bắt buộc invalid citation bị loại và câu trả lời fail-closed; sửa mapping/retrieval unit và kiểm chứng source click-through. |
| Disclaimer/guardrail thiếu hoặc sai mode | Sửa đường response, bao gồm nhánh deterministic/deflect/SSE; test từng branch và lịch sử mở lại. |
| UI hiển thị sai hoặc mất metadata | Sửa serializer/API contract/UI; E2E kiểm tra SSE `done` và lịch sử có cùng metadata. |
| Hạ tầng timeout/DB/object storage | Retry an toàn, trace lỗi, không biến lỗi thành câu trả lời thiếu căn cứ giả; thông báo người dùng bằng tiếng Việt và cung cấp mã hỗ trợ. |

Trạng thái quality issue: `reported -> triaged -> reproduced -> fix_in_progress -> regression_added -> verified -> closed`. `not_reproducible` và `accepted_risk` cần bằng chứng, người quyết định và ngày xem xét lại; không được dùng để bỏ qua lỗi pháp lý nghiêm trọng.

Mỗi lỗi được gắn `root_cause_family` và phạm vi ảnh hưởng: parser/format, source/version, metadata/temporal, retrieval/ranking, verifier/generation, API/stream, UI hoặc hạ tầng. Trước khi sửa phải tìm các lỗi cùng family và các consumer/route/parser dùng chung; lập danh sách nhánh tương tự cần kiểm tra. Nếu một lỗi tái diễn sau khi đã đóng, mở lại issue family và xử lý nguyên nhân gốc/thiết kế chung, không vá riêng instance mới.

**Ứng phó sự cố nghiêm trọng:** Sai căn cứ, dùng nguồn inactive, thiếu disclaimer hoặc claim high-risk không hỗ trợ: tắt/ suspend phần bị ảnh hưởng, giữ log/evidence, xác định câu trả lời bị ảnh hưởng, tạo regression, re-evaluate và chỉ bật lại sau khi người chịu trách nhiệm duyệt.

### Giai đoạn 7 — Bộ regression và release evaluation

- Xây fixture DOCX tổng hợp cho format: nested table/merged cells, numbering, hidden text, comments, tracked changes, headers/footers, footnotes, image-only/embedded, hyperlink, section break, malformed package và invisible Unicode.
- Mỗi production parse bug được tái hiện bằng fixture tối thiểu đã kiểm tra quyền lưu; test phải thất bại trước khi sửa và pass sau khi sửa.
- Mỗi bug fix phải có regression theo **họ lỗi**, không chỉ một input: kiểm thử mọi biến thể cùng cấu trúc/OOXML part, mọi parser dùng chung, đường upload thường và thay file, draft/published, public/admin nếu liên quan. Bổ sung ca negative để xác nhận phần không hỗ trợ vẫn bị chặn.
- Với lỗi RAG/API/UI, chạy test ở component gây lỗi và các nhánh tiêu thụ contract đó (SSE `done`, lịch sử chat, citation click-through, public/admin view); kiểm tra không làm sai hành vi đúng trước đây.
- Đóng issue chỉ khi test reproduction thất bại trước fix, pass sau fix, bộ test liên quan pass, và full CI/eval được chạy theo mức ảnh hưởng. Lỗi parser/RAG/security/corpus cần full regression và golden eval; lỗi thuần UI vẫn cần E2E cho breakpoint/role liên quan.
- Theo dõi recurrence theo `root_cause_family`; tái diễn làm tăng severity và bắt buộc xem lại giải pháp chung. Không đạt chỉ vì cùng một fixture cũ đã pass.
- Golden case phải được gán nhãn từ nguồn đối chiếu độc lập, có thời điểm áp dụng, Điều/Khoản, claim bắt buộc, hành vi mong đợi và loại guardrail. Không sửa kỳ vọng chỉ để khớp model.
- Duy trì holdout; báo cáo số case chạy/skip/invalid/evaluator error, corpus/parser/model/prompt version và latency.
- Bao gồm câu hỏi paraphrase, sai chính tả/không dấu, hỏi số hiệu, follow-up, đa văn bản, near-tie, bảng, phụ lục, historical, thiếu dữ kiện, ngoài scope và prompt injection.

**Release gate theo đặc tả hiện hành:** dataset đầy đủ, không invalid/skip ngoài chính sách; không active-filter violation/high-risk unsupported claim/missing disclaimer; hallucination rate <= 2%; faithfulness >= 0.90 trung bình và >= 0.80 mỗi case; citation accuracy >= 0.98; coverage bắt buộc 100%; prompt injection, legal strategy block và historical isolation 100%; P95 <= 5 giây. Đạt metric không thay thế review pháp lý.

### Giai đoạn 8 — End-to-end, bảo mật và accessibility

- E2E guest chat/public search; đăng ký/đăng nhập; user chỉ truy cập session của mình; admin upload/review/publish/suspend/replacement; quality issue review.
- Test source download, CORS, rate limit, JWT expiry/role, upload size/type, checksum duplicate, presigned URL và lỗi object storage.
- Kiểm tra text overflow, keyboard/focus/labels, empty/loading/error state ở desktop/mobile; không lộ UUID/stack trace/secret.
- Tách smoke test staging khỏi test cần key/service thật; test lỗi provider phải xác nhận fail closed.

**Cổng qua:** luồng trọng yếu chạy liên tục qua UI/API, không chỉ unit tests; không có lỗi bảo mật mức critical/high chưa xử lý.

### Giai đoạn 9 — Staging, backup, khôi phục và phát hành pilot

- Tách local/staging/production bằng database, bucket, JWT secret và OpenAI credentials riêng; secrets không vào Git.
- Deploy frontend/API, chạy Alembic, cấu hình CORS/API URL, object storage; xác nhận upload, download, SSE streaming và cold start.
- Không dùng filesystem ephemeral làm kho file. Backup PostgreSQL và R2/source assets theo cùng mốc; thử restore sang môi trường cô lập, đối chiếu row count, URI, checksum và source click-through.
- Dùng Render/Vercel/Neon/R2 free tier chỉ cho demo/staging nếu các điều kiện gói phù hợp; đánh giá chi phí OpenAI, giới hạn ngủ/compute/storage, commercial-use terms, backup và uptime trước pilot công khai.
- Tạo release checklist, rollback plan, owner trực xử lý và cách suspend chủ đề/revision. Không phát hành nếu chưa có restore test và corpus pilot chưa được duyệt.

### Giai đoạn 10 — Bảo trì định kỳ

- Mỗi lần nhập nguồn: kiểm checksum/duplicate -> parse report -> xử lý toàn bộ critical issue -> review -> publish -> golden regression -> kiểm click-through.
- Định kỳ rà văn bản mới/sửa đổi/hết hiệu lực; cập nhật hiệu lực theo từng provision khi cần, không chỉ theo document status.
- Hàng tháng kiểm backup/restore, lỗi parser, issue quá hạn, false abstention, latency, quota/chi phí và tỷ lệ nguồn hỏng.
- Mỗi parser/prompt/ranker/model change phải version hóa; chạy test fixture + evaluation so sánh trước/sau.
- Có quy trình sự cố: suspend nguồn/chủ đề -> giữ evidence/log -> xác định phạm vi ảnh hưởng -> sửa nguồn/code -> regression/eval -> người duyệt xác nhận -> publish lại.

## 4. Hợp đồng bắt buộc cho mọi lỗi

Không issue nào được đóng chỉ vì đã hiện cảnh báo. Trước khi đóng, phải có đủ:

1. **Phát hiện:** mã lỗi ổn định, severity, revision/checksum/parser hoặc request/trace ID.
2. **Phạm vi ảnh hưởng:** part, block/node, locator, retrieval unit, câu trả lời/chủ đề bị ảnh hưởng.
3. **An toàn tức thời:** có được dùng để trả lời không; nếu chưa rõ thì mặc định không answerable.
4. **Cách sửa:** retry, reparse, sửa mapping, source/rendition mới, code fix, metadata/legal review hoặc loại khỏi phạm vi.
5. **Chạy lại:** thao tác và version cần dùng; phải idempotent, giữ nguyên source gốc và audit.
6. **Xác minh:** đối chiếu nguồn, kiểm parser output/citation, regression/eval hoặc smoke test tương ứng.
7. **Đóng/rollback:** actor, bằng chứng, trạng thái trước/sau; nếu sửa không đạt thì khôi phục bản an toàn hoặc giữ chủ đề tắt.
8. **Không tái phạm:** ghi `root_cause_family`, xác định các luồng/parser/consumer liên quan, thêm regression theo biến thể và chạy đúng phạm vi CI/eval trước khi đóng.

Reviewer quyết định ý nghĩa pháp lý và answerability. Reviewer không phải tự sửa parser, SQL, embedding hay deployment; lỗi kỹ thuật phải tạo engineering issue có reproduction artifact để Codex có thể sửa và thêm regression.

Thông báo cho reviewer luôn là tiếng Việt có dấu và mô tả nghiệp vụ. Chi tiết kỹ thuật được giữ đầy đủ nhưng nằm ở phần thu gọn/copy được, để người vận hành đọc dễ còn Codex/dev có đủ mã lỗi, vị trí, version, hash và trace để tái hiện.

## 5. Thứ tự ưu tiên đề xuất

1. Làm xanh CI và lấy lại baseline test đáng tin cậy.
2. Xây package inventory/parse report + stable issue codes; trước mắt block publish khi có part chưa phân loại.
3. Khôi phục/chuẩn hóa corpus manifest theo nguồn chính thức và chọn pilot.
4. Bổ sung parser fixtures cho các format nội bộ và hidden content; xử lý các regression được phát hiện.
5. Hoàn thiện answer-quality issue loop và fail-closed remediation.
6. Chạy full evaluation trên corpus pilot, xử lý từng failure theo root-cause matrix.
7. Deploy staging, kiểm tra backup/restore và E2E; sau đó mới quyết định mở pilot.

## 6. Điều kiện tuyên bố hoàn thành

- Phạm vi pilot và nguồn được người có trách nhiệm duyệt.
- Mọi package part trong nguồn pilot được extract, review-only hoặc loại có lý do; không còn phần chưa biết có thể ảnh hưởng nghĩa.
- Không còn parse issue critical/high chưa resolved; mọi issue đã đóng có regression theo root-cause family và bằng chứng xác minh phù hợp.
- Mọi lỗi reviewer nhìn thấy đều có nội dung tiếng Việt có dấu, giải thích ảnh hưởng, trạng thái answerability, hành động an toàn và cách xác nhận hoàn tất; chi tiết kỹ thuật vẫn truy được.
- Mọi fix có danh sách nhánh liên quan đã kiểm tra; recurrence của lỗi cùng family được theo dõi và xử lý ở nguyên nhân chung.
- Mọi câu trả lời pilot có citation hợp lệ hoặc abstain, disclaimer đúng, active/temporal filter đúng.
- Backend/frontend/DB integration/E2E/full eval/release gates đạt trong CI hoặc release environment có thể tái lập.
- Staging chạy được; backup và restore cả database lẫn source assets đã thử; có rollback/suspend runbook.
- Mọi unknown được công khai là giới hạn sản phẩm, không được biến thành câu trả lời suy đoán.
