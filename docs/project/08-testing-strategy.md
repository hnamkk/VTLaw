# Chiến Lược Kiểm Thử
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

| Mục | Nội dung |
|---|---|
| Framework chính | `pytest`, `pytest-asyncio`, Playwright |
| Frontend checks | `npm run lint`, `npm run build` |
| E2E UI | `npm run e2e:ui` hoặc `python scripts/e2e_ui_audit.py` |
| Cập nhật gần nhất | 09/07/2026 |

---

## 1. Mục tiêu

- Khóa các yêu cầu bất biến của public/chat/admin sau R1-R5.
- Chặn hồi quy quay lại dữ liệu cũ hoặc route legacy.
- Bảo đảm UI không lộ text hỏng, thuật ngữ nội bộ hoặc overlay lỗi.
- Bảo đảm `Kho văn bản` admin hoạt động với dữ liệu thật, không né lỗi bằng payload rỗng.

---

## 2. Các lớp kiểm thử

| Lớp | Mục tiêu |
|---|---|
| Unit test | Logic thuần: parsing, retrieval helper, guardrail, ranking |
| API test | Contract request/response, RBAC, serialization, fallback lỗi |
| Integration test | Query DB, publish/suspend workflow, retrieval gates |
| E2E UI | Xác nhận network status, nội dung hiển thị, active view, snapshot desktop/mobile |

---

## 3. Regression bắt buộc

### 3.1 Public và chat

- Public documents chỉ đọc từ revision `published`.
- Văn bản `suspended` không xuất hiện trên public surface.
- Chat chỉ dùng retrieval unit đã duyệt, đang công bố và không `suspended`.
- Không được fallback từ public/chat về `LegalDocument` hoặc `document_chunks`.
- Historical citation vẫn mở được để giữ provenance, nhưng không được làm sống lại dữ liệu `suspended` trong public list hoặc chatbot.

### 3.2 Admin `Kho văn bản`

- `GET /api/v1/admin/kb-v2/documents` phải trả dữ liệu thật cho màn hình quản trị.
- Response phải giữ các field UI đang dùng: `revision_id`, `summary`, `source`, `relations`, `display_status`.
- Serialization phải eager-load đủ quan hệ để không phát sinh `MissingGreenlet`.
- Lỗi fallback phải là tiếng Việt dễ hiểu; không để lộ `Internal Server Error`.
- `Duyệt văn bản` phải có API test riêng cho hai route `GET /api/v1/admin/kb-v2/revisions` và `GET /api/v1/admin/kb-v2/revisions/{revision_id}` để khóa trường hợp serializer ném exception nhưng UI vẫn chỉ nhận `detail.code` và thông điệp tiếng Việt sạch.

### 3.3 Runtime cutover

- `main.py` không mount route legacy `admin_kb.py`.
- Runtime agent/tool không import `src.rag.retrieval.hybrid`.
- Script publish/reconcile cũ chỉ chạy khi có `--legacy-allow`.
- Settings/runtime không còn phụ thuộc `KB_V2_*`; chỉ còn các cấu hình đang dùng như `KB_REQUIRE_OBJECT_STORAGE` và `KB_LOCAL_STORAGE_PATH`.

---

## 4. Bộ test hiện hành

### 4.1 Pytest backend

- `app/backend/tests/test_api/test_admin_kb_v2.py`
- `app/backend/tests/test_api/test_chat.py`
- `app/backend/tests/test_api/test_documents.py`
- `app/backend/tests/test_api/test_routes.py`
- `app/backend/tests/test_api/test_auth.py`
- `app/backend/tests/test_rag/test_agent.py`
- `app/backend/tests/test_rag/test_retrieval.py`
- `app/backend/tests/test_rag/test_metadata_extraction.py`
- `app/backend/tests/test_rag/test_policy.py`
- `app/backend/tests/test_rag/test_response_metadata.py`
- `app/backend/tests/test_rag/test_follow_up.py`
- `app/backend/tests/test_rag/test_kb_v2_answering.py`
- `app/backend/tests/test_rag/test_kb_v2_parser.py`
- `app/backend/tests/test_rag/test_kb_v2_publication.py`
- `app/backend/tests/test_rag/test_publish_effective_documents.py`
- `app/backend/tests/test_rag/test_kb_cutover_runtime.py`
- `app/backend/tests/test_e2e_ui_audit.py`

`test_kb_v2_publication.py` bao gồm regression cho citation builder: retrieval unit phải dựng trích dẫn từ `structured_content.article_num`, `clause_num`, `point_num` và không được kế thừa nhầm Điều từ parent cũ.

`test_response_metadata.py` khóa contract metadata cho chat:

- default schema giữ backward compatibility với `citations`
- chỉ map sang `provision_citations` khi citation còn `active` và `verification_status` là `verified` hoặc `partial`
- direct response/guardrail phải gán đúng `answer_mode`
- summary/metadata path phải có `document_sources` khi backend đã có nguồn văn bản
- citation inactive/historical không được lọt vào `provision_citations` và phải đứng riêng ở `historical_references`

`test_policy.py` khóa rule deterministic cho `risk_level` và `answer_mode`:

- fixture low/medium/high theo intent và loại câu hỏi
- câu hỏi chiến lược kiểu `Tôi nên làm gì`, `có nên khiếu nại/khởi kiện` phải ra `risk_level=high`
- câu hỏi ngoài phạm vi/prompt injection không được gán `direct`
- `low_confidence` phải rơi về `insufficient_evidence`
- câu `Toi nen lam gi de dang ky...` kiểu thủ tục phải vẫn đi theo `procedure`, không bị chặn như legal strategy
- câu `Toi nen kien khong?`, `Lam sao de tranh bi phat?` phải rơi vào `legal_advice_boundary` và không tạo lời khuyên cá nhân hóa

`test_follow_up.py` khóa resolver trước retrieval:

- follow-up rõ thì mới ghép history vào `retrieval_query`
- history mơ hồ hoặc history chứa prompt injection phải rơi về `clarification_needed`
- user đổi chủ đề mới không bị kéo theo history cũ
- history co intent `comparison_history` van co the duoc xem la topic du ro cho cau follow-up ve hien hanh

`test_kb_v2_answering.py` khoa regression C5:

- active filter mac dinh van buoc `legal_status=\'active\'` va `answerable_status=\'active\'`
- historical mode la path rieng, khong lam rong eligibility filter active mode
- `effective_status` cho van ban da het hieu luc phai tra lifecycle metadata thay vi generic not-found
- `comparison_history` phai tra `historical_references` va answer text neu ro khong phai can cu hien hanh
- nhieu moc ngay hoac nhieu giai doan historical chua neu moc nao phai roi ve clarification
- query tong quat nhieu van ban phai khoa notice vai tro theo thu tu `Luat -> Nghi dinh -> Thong tu`
- near-tie khac huong phai co fixture tach ba nhanh `evidence_clarification`, `evidence_multiple_possibilities`, `evidence_insufficient`

`test_routes.py` khóa contract SSE của `POST /api/v1/chat/stream`:

- nhánh có citation vẫn phải trả đủ `citations`, `document_sources` và guardrail metadata
- nhánh `clarification_needed` phải giữ `answer_mode` và `clarification_question` trong `done` payload để client không mất trạng thái khi parse stream
- nhánh redirect legal strategy phải vẫn đẩy `risk_level=high` qua metadata, không nhét risk text vào answer

`test_api/test_chat.py` khóa helper history ở API layer:

- `conversation_context` chỉ là ngữ cảnh hội thoại, không giữ disclaimer cũ như evidence
- không có history thì trả chuỗi rỗng, không crash
- assistant message mới có `response_metadata` phải được `GET /chat/sessions/{session_id}/messages` trả lại nguyên để UI không mất `historical_references`, `document_sources`, `risk_level` hoặc `answer_mode` khi mở lại lịch sử

`test_kb_v2_parser.py` khóa hai invariant: Điều chỉ có tiêu đề vẫn phải có node
cha `structural_only`, và nội dung sau heading phụ lục không được sinh Điều/Khoản
dùng cho hỏi đáp. Câu nhắc tên phụ lục bên trong Khoản không được kích hoạt vùng
phụ lục.

### 4.2 Frontend checks

- `npm run lint`
- `npm run build`
- Chat UI phải render được field mới khi có và fallback được response cũ chỉ có `citations`.
- Panel `Thông tin bổ sung` phải hiển thị mode/risk/confidence, căn cứ hiện hành, nguồn tổng quan và tham chiếu lịch sử tách biệt.

### 4.3 E2E UI lặp lại được

- Runner: `scripts/e2e_ui_audit.py`
- Cấu hình: `app/frontend/playwright.config.ts`
- Spec: `app/frontend/e2e/ui-audit.spec.ts`
- Regression Kho/Duyệt: `app/frontend/e2e/admin-kb-regression.spec.ts`
- Regression Tra cứu public: `app/frontend/e2e/public-search-regression.spec.ts`
- Regression chat clarification/history: `app/frontend/e2e/chat-clarification-regression.spec.ts`
- Lệnh nhanh: `npm run e2e:ui`

#### Gate của E2E

- Không hardcode credential; dùng `E2E_ADMIN_EMAIL` và `E2E_ADMIN_PASSWORD`.
- Không log password hoặc token.
- Assert network status của các request trọng yếu.
- Fail nếu còn text cấm, mojibake, overlay lỗi ứng dụng hoặc active view sai.
- Chụp snapshot desktop/mobile cho public và admin.
- Không thực hiện thao tác ghi dữ liệu nếu không có cơ chế an toàn; nếu cần bootstrap admin tạm thì phải rollback sau test.
- Đối chiếu động `relation_count` cho toàn bộ `document_id` giao nhau giữa Kho và Duyệt, phân trang đến hết dữ liệu và không hardcode một số hiệu mẫu.
- Xác nhận modal lưu mở hộp thoại tùy biến và không gọi `window.confirm`.
- Khi kiểm tra lưu thông tin, E2E phải tạo một thay đổi cục bộ rồi mở confirmation và hủy; không gửi request ghi dữ liệu. Form nguyên trạng phải giữ thông báo không có thay đổi thay vì mở confirmation vô ích.
- Ở mobile, xác nhận nhóm category không gây overflow hoặc cắt card.
- Kiểm tra tiến trình upload bằng cách chặn request trong trình duyệt; fixture không được gửi tới backend và không ghi database.
- Kiểm tra luồng `Thay file nguồn` bằng request upload bị mock trong trình duyệt: modal phải cuộn tới footer trên desktop/mobile, khóa backdrop/nút đóng/nút hủy khi đang xử lý, hiển thị tiến trình bốn bước và chuyển sang `Duyệt văn bản` bằng đúng `revision_id` trả về thay vì tìm theo tiêu đề.
- Snapshot Kho/Duyệt phải chờ `.kb-loading-copy` ẩn và `.kb-list-skeleton` được gỡ khỏi DOM trước khi thu thập nội dung hoặc chụp ảnh.
- Regression Tra cứu public phải chọn dữ liệu động từ API `/api/v1/documents`, không hardcode một số hiệu mẫu; nếu có văn bản có quan hệ thì phải xác nhận quan hệ public hiển thị khớp dữ liệu API, còn nếu không có quan hệ thì bài test vẫn kiểm tra search/card/source modal tổng quát.

---

## 5. Bằng chứng kiểm thử sau R5

| Hạng mục | Kết quả gần nhất |
|---|---|
| `npm run lint` | Đạt |
| `npm run build` | Đạt |
| `pytest app/backend/tests/test_e2e_ui_audit.py -q` | Đạt |
| `python scripts/e2e_ui_audit.py --start-backend --start-frontend --bootstrap-admin-if-missing` | Đạt |
| Public/Admin E2E audit | `15 passed`, `1 skipped` |
| API documents unit | `9 passed` |

Artifact hiện hành:

- `e2e-snapshots-live/ui-audit-results.json`
- `e2e-admin-snapshots/admin-ui-audit-results.json`
- snapshot desktop/mobile trong hai thư mục trên

---

## 6. Tiêu chí chặn phát hành

- Có request `401`, `403`, `500` bất thường trên flow public/admin trọng yếu.
- UI còn text hỏng, chữ không dấu do fallback lỗi, hoặc thuật ngữ nội bộ bị lộ ở phần user-facing.
- `Kho văn bản` admin trả payload thiếu field đang được UI dùng.
- Public/chat dùng lại dữ liệu legacy hoặc route legacy được mount trở lại.
- `git diff --check` phát hiện lỗi whitespace/diff format mới.

---

## 7. Ghi chú vận hành

- Snapshot E2E là bằng chứng smoke vận hành, không thay thế toàn bộ bài test nghiệp vụ sâu.
- Chat E2E nên tiếp tục ưu tiên bài kiểm có mock hoặc môi trường khóa chi phí để không phát sinh gọi LLM ngoài ý muốn.
- Khi bổ sung hành vi public/chat/admin mới, phải cập nhật tài liệu này và bổ sung gate tương ứng.

## 8. Regression dữ liệu KB v2

- `test_kb_v2_publication.py` khóa guard publish với `clause`/`point` mồ côi: revision không được công bố hoặc công bố lại nếu Khoản/Điểm chưa gắn đúng cha.
- Revision đã `published` nhưng `review_status` lệch chỉ được chuẩn hóa về `approved` sau khi toàn bộ publish blockers đều sạch.
- Audit vận hành sau rebuild phải chạy `scripts/rebuild_kb_v2_structure.py` dry-run, `scripts/rebuild_kb_v2_citations.py` dry-run và kiểm tra retrieval unit active/historical trước khi đóng batch dữ liệu.

## 9. Query policy regression

- `test_query_policy.py` validates the versioned config at `app/backend/src/rag/policies/query_policy.json`.
- Minimum regression expectations:
  - default config parses successfully
  - deterministic query expansion still matches the configured rules
  - intent and legal-advice helpers still read the configured hints
  - invalid config with duplicate values or unknown term-group references fails validation
  - startup validation uses the same loader path so config errors fail early

## 10. Golden eval coverage

- `app/backend/tests/test_rag/test_eval.py` khoa dataset schema, dataset quality va deterministic release-gate helper.
- Golden dataset hien tai co file `eval/golden/chat_behavior_cases.jsonl` de khoa cac behavior chat da implement:
  - `answer_mode=direct` voi `provision_citations`
  - `answer_mode=summary` voi `document_sources`
  - `answer_mode=historical` voi `historical_references`
  - follow-up resolved bang `conversation_context`
  - follow-up mo ho tra `clarification_needed`
  - `multiple_possibilities` cho near-tie va legal-advice redirect
  - prompt injection doi bo citation/disclaimer
- Golden dataset co them `eval/golden/production_coverage_cases.jsonl` de nang
  coverage len 145 case, tap trung vao production readiness: legal advice,
  follow-up, historical, temporal, multi-document, citation metadata va
  insufficient evidence.
- `eval/run_eval.py` hien validate them `expected_answer_mode`,
  `expected_risk_level`, `min_provision_citations`, `min_document_sources`,
  `min_historical_references` va `require_clarification_question`.
- Release gate chia 3 lop:
  - blocker: active filter, disclaimer, prompt injection, legal-advice boundary,
    historical/provision separation va metadata contract completeness
  - release quality: faithfulness floor, citation accuracy, hallucination,
    OOS/safe abstention, false abstention, answer mode/risk/follow-up accuracy va P95 latency
  - warning: faithfulness target 0.92, answer relevancy va answerable abstention
