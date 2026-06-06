# AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải
## TÀI LIỆU Bước 2: PRD - Product Requirements Document

**Người lập:** AI Software Design Engineer  
**Ngày tạo:** 06/06/2026  
**Dựa trên:** Bước 1 - Research Brief (05/06/2026)

---

## MỤC LỤC

1. [User Stories](#1-user-stories)
2. [Functional Requirements](#2-functional-requirements)
3. [Non-Functional Requirements](#3-non-functional-requirements)
4. [Luồng xử lý chính - System Flow](#4-luồng-xử-lý-chính--system-flow)
5. [Data Model sơ bộ](#5-data-model-sơ-bộ)
6. [Phân kỳ triển khai MVP](#6-phân-kỳ-triển-khai-mvp)
7. [Tính năng sáng tạo](#tính-năng-sáng-tạo)

---

## 1. User Stories

Viết theo format chuẩn: **"Là [role], tôi muốn [action] để [benefit]"**

### 1.1 Người dùng tra cứu luật (USER)

| ID | User Story | Priority |
|---|---|---|
| US-US01 | Là **người dùng (USER)**, tôi muốn **đặt câu hỏi bằng ngôn ngữ tự nhiên tiếng Việt về quy định vận tải** để **nhận câu trả lời nhanh chóng (< 30 giây) mà không bị ngợp bởi các thuật ngữ pháp lý phức tạp**. | Must |
| US-US02 | Là **người dùng (USER)**, tôi muốn **hệ thống chỉ trả lời dựa trên văn bản pháp luật còn hiệu lực (metadata `status=active`) và tự động cảnh báo/hướng dẫn nếu hỏi về văn bản đã hết hiệu lực** để **tránh áp dụng NĐ 100/2019 hoặc chọn sai nguồn hiện hành theo nhóm nội dung**. | Must |
| US-US03 | Là **người dùng (USER)**, tôi muốn **nhận câu trả lời kèm trích dẫn chi tiết Điều, Khoản cụ thể và có thể click-through để xem trực tiếp đoạn văn bản gốc có highlight** để **tự kiểm chứng và tăng độ tin cậy của thông tin**. | Must |
| US-US04 | Là **người dùng (USER)**, tôi muốn **được cảnh báo và hướng dẫn áp dụng khi hai văn bản pháp lý mâu thuẫn hoặc chồng chéo về cùng một vấn đề** để **không bị bối rối và hạn chế rủi ro pháp lý**. | Must |
| US-US05 | Là **người dùng (USER)**, tôi muốn **lưu/bookmark các cuộc trò chuyện quan trọng và đặt tên dễ nhớ** để **mở lại toàn bộ phiên hỏi đáp khi cần xem lại**. | Should |
| US-US06 | Là **người dùng (USER)**, tôi muốn **nhận thông báo in-app realtime khi ADMIN duyệt văn bản mới/cập nhật hiệu lực và vẫn xem lại được khi đăng nhập sau** để **kịp thời cập nhật quy định mới**. | Should |
| US-US07 | Là **người dùng (USER)**, tôi muốn **truy cập hệ thống mượt mà trên cả máy tính và điện thoại thông qua giao diện Web Responsive** để **có thể tra cứu mọi lúc mọi nơi**. | Should |

### 1.2 Quản trị viên hệ thống (ADMIN)

| ID | User Story | Priority |
|---|---|---|
| US-AD01 | Là **quản trị viên (ADMIN)**, tôi muốn **tải file văn bản pháp luật (PDF/Word) thủ công lên hệ thống một cách dễ dàng và trực quan** để **cập nhật Knowledge Base kịp thời mà không cần dùng hệ thống crawler tự động phức tạp**. | Must |
| US-AD02 | Là **quản trị viên (ADMIN)**, tôi muốn **kiểm tra metadata tự động trích xuất và phê duyệt/từ chối văn bản trước khi đưa vào KB (human-in-the-loop)** để **đảm bảo độ chính xác tuyệt đối và tuân thủ Luật AI 134/2025/QH15**. | Must |
| US-AD03 | Là **quản trị viên (ADMIN)**, tôi muốn **có dashboard theo dõi các chỉ số chất lượng AI (Faithfulness, Answer Relevance, Hallucination Rate)** để **kịp thời phát hiện sự suy giảm hiệu năng của chatbot**. | Must |
| US-AD04 | Là **quản trị viên (ADMIN)**, tôi muốn **quản lý danh sách người dùng (CRUD user), gán role (USER/ADMIN), và kích hoạt hoặc khóa tài khoản** để **kiểm soát quyền truy cập hệ thống một cách an toàn**. | Must |

---

## 2. Functional Requirements

### 2.1 Core Features (Bắt buộc - MVP)

| # | Tính năng | Mô tả chi tiết |
|---|---|---|
| F01 | **Knowledge Base - Văn bản Pháp luật GTVT** | Tải lên thủ công và index các văn bản pháp luật vận tải đường bộ VN (Luật, Nghị định, Thông tư) từ các file định dạng PDF/Word do ADMIN cung cấp qua KB Manager. Mỗi chunk có metadata bắt buộc: `{ status: active/repealed, effective_date, expiry_date, replaced_by, van_ban_id, dieu, khoan, diem }`. Hierarchical chunking bảo toàn cấu trúc Chương → Điều → Khoản → Điểm. |
| F02 | **Metadata Active Filter - Bắt buộc trước Retrieval** | Mọi truy vấn RAG BẮT BUỘC lọc `status=active` TRƯỚC khi vector search - không thể bypass. Khi người dùng hỏi văn bản hết hiệu lực, hệ thống cảnh báo và chỉ nêu nguồn active phù hợp với nội dung đang hỏi; không tự khẳng định một văn bản thay thế toàn bộ nếu quan hệ pháp lý không đủ rõ. Zero-tolerance: không có exception. |
| F03 | **Q&A Pháp luật - Chat Interface** | Người dùng đặt câu hỏi bằng tiếng Việt tự nhiên. LLM sinh câu trả lời STRICTLY chỉ dựa trên context đã retrieve (không suy diễn ngoài KB). Trường hợp có nhiều thông tin khác nhau/mâu thuẫn được retrieve, hiển thị tất cả nguồn để người dùng tự đối chiếu. Mỗi trả lời bắt buộc kèm: [1] trích dẫn Điều-Khoản cụ thể có thể click-through xem văn bản gốc, [2] tên văn bản + ngày hiệu lực, [3] disclaimer theo mẫu chuẩn. |
| F04 | **Citation Verifier - Grounded Generation** | Sau khi LLM sinh trả lời, Citation Verifier đối chiếu từng trích dẫn với chunk gốc trong KB. Nếu không verify được → đánh dấu "Chưa xác minh" và cảnh báo người dùng kiểm tra thủ công. Hallucination rate mục tiêu < 5%. |
| F05 | **Guardrail Disclaimer - 100% Legal Outputs** | Mọi output có nội dung pháp lý BẮT BUỘC kèm disclaimer: *"Thông tin này do hệ thống AI tổng hợp, chỉ mang tính tham khảo và không thay thế ý kiến tư vấn pháp lý chuyên nghiệp. Để có biện pháp chính thức, vui lòng tham khảo luật sư hoặc cơ quan có thẩm quyền."* Disclaimer không thể tắt được, hiển thị rõ - tuân thủ Luật AI 134/2025/QH15. |
| F07 | **Alert System - In-app Notifications** | Hệ thống tự động tạo thông báo khi ADMIN duyệt/publish văn bản, lưu trạng thái đọc theo USER và broadcast realtime qua SSE cho người dùng đang đăng nhập; USER đăng nhập sau vẫn xem được danh sách thông báo. |
| F08 | **Out-of-scope Filter** | Tự động phát hiện câu hỏi ngoài phạm vi vận tải đường bộ VN (hình sự, thuế, luật nước ngoài...) và từ chối lịch sự, hướng dẫn người dùng tìm nguồn phù hợp. Deflection rate mục tiêu ≥ 90%. |
| F09 | **Lịch sử & Đã lưu** | Lưu lịch sử Q&A theo phiên trong màn `Hỏi đáp pháp luật`. USER có thể bookmark một phiên hội thoại, đặt tên hiển thị và xem lại trong mục `Đã lưu`; khi bấm thẻ đã lưu, hệ thống mở lại toàn bộ session trong `Hỏi đáp pháp luật`. |
| F10 | **User Management - Quản lý Người dùng** | ADMIN quản lý danh sách tài khoản người dùng, thực hiện CRUD tài khoản, phân quyền vai trò (USER/ADMIN), kích hoạt hoặc khóa tài khoản. |

### 2.2 Nice-to-Have Features (Mở rộng - Phase 2+)

| # | Tính năng | Mô tả |
|---|---|---|
| N03 | **Knowledge Graph RAG (KG-RAG Hybrid)** | Tích hợp Knowledge Graph để xử lý câu hỏi đa văn bản phức tạp, truy vết quan hệ giữa các Điều-Khoản, tăng độ chính xác từ 80% lên ~85.7% (theo nghiên cứu KG-RAG VN pháp luật 2025). |
| N06 | **So sánh văn bản luật cũ vs mới** | Cho phép so sánh theo nhóm nội dung giữa văn bản cũ và các nguồn hiện hành liên quan (ví dụ NĐ 100 với NĐ 168 hoặc NĐ 336), hiển thị rõ phạm vi và điều khoản thay đổi. |
| N07 | **AI Lawyer Referral** | Khi phát hiện câu hỏi vượt khả năng RAG hoặc có mâu thuẫn pháp lý phức tạp, gợi ý kết nối chuyên gia pháp lý đối tác (MOU với công ty luật chuyên GTVT). |
| N08 | **Conflict Detection - Phát hiện Mâu thuẫn Văn bản** | Khi câu hỏi liên quan đến nhiều văn bản, hệ thống phát hiện và hiển thị cảnh báo nếu các văn bản mâu thuẫn nhau (cần KG-RAG N03). Giải thích quy tắc ưu tiên áp dụng (luật sau ưu tiên hơn luật trước, luật ưu tiên hơn nghị định). |

---

## 3. Non-Functional Requirements

| Yêu cầu | Mức chỉ tiêu |
|---|---|
| **Performance - Q&A** | P95 < 5 giây/câu hỏi; TTFT (streaming) < 2 giây |
| **In-app Alert Latency** | Hiển thị tức thời (in-app) ngay sau khi ADMIN phê duyệt xuất bản văn bản mới |
| **Availability** | Uptime ≥ 99.5% (≈ ~3.6h downtime/tháng) |
| **Scalability** | 100 concurrent users/instance; scale horizontal khi vượt ngưỡng |
| **AI Accuracy - Hallucination Rate** | < 5% (citation verifier + manual review hàng tháng) |
| **Active Filter Accuracy** | 100% - zero tolerance, văn bản hết hiệu lực tuyệt đối không được trả lại |
| **Out-of-scope Deflection** | ≥ 90% |
| **Security** | Encryption at rest (AES-256) + in transit (TLS 1.3); RBAC theo vai trò (USER/ADMIN); log hoạt động hệ thống đầy đủ |
| **Compliance - AI Law** | Tuân thủ Luật AI 134/2025/QH15 (hiệu lực 01/03/2026): phân loại medium-risk, human-in-the-loop KB update, transparency bắt buộc |
| **Compliance - PDPD** | Dữ liệu người dùng không dùng để train model |
| **Usability** | Chat interface quen thuộc (zero training required); trích dẫn có thể click-through xem văn bản gốc |
| **Responsive** | Web Responsive (hoạt động tốt trên cả trình duyệt Desktop và Mobile) |
| **Data Retention** | Lịch sử Q&A lưu trữ tối thiểu 1 năm; KB archive vĩnh viễn |
| **Audit Trail** | Ghi log: ai hỏi gì, AI trả lời gì, trích dẫn từ văn bản nào, faithfulness score, latency, người thực hiện hành động |


---

## 4. Luồng xử lý chính - System Flow

### 4.1 Bối cảnh vận hành (Context)

Hệ thống phục vụ hai nhóm người dùng chính:

- **USER (Người tra cứu luật):** Tra cứu nhanh các quy định, mức phạt, hướng xử lý tình huống giao thông, lưu/bookmark các cuộc trò chuyện quan trọng, mở lại lịch sử Q&A theo session và nhận thông báo in-app khi có luật mới được ban hành hoặc cập nhật.
- **ADMIN (Quản trị viên):** Tải văn bản lên thủ công qua giao diện quản trị, duyệt và gán metadata cho văn bản (HITL), quản lý người dùng (thêm, xóa, phân quyền) và theo dõi chất lượng hệ thống thông qua dashboard AI.

Hệ thống đóng vai trò như một **"Trợ lý AI tra cứu & tuân thủ quy định giao thông vận tải"** 24/7 trực quan, chính xác và minh bạch.

### 4.2 Luồng TO-BE - Q&A Chat (Happy Path)

```
┌─────────────────┐     ┌───────────────────┐     ┌──────────────────────────┐
│  USER đặt       │────>│ Intent Classifier │────>│  Metadata Active Filter  │
│  câu hỏi        │     │ (Phân loại ý định │     │  status=active BẮT BUỘC  │
│  tiếng Việt     │     │  hoặc Fast Embed) │     │  TRƯỚC vector search     │
└─────────────────┘     └───────────────────┘     └──────────────┬───────────┘
                                                                 │
                                                   ┌─────────────▼────────────┐
                                                   │   Hybrid Retriever       │
                                                   │ pgvector + BM25          │
                                                   └─────────────┬────────────┘
                                                                 │
                          ┌──────────────────────────────────────▼───────────┐
                          │                  LLM Generator                   │
                          │  GPT-4o-mini - Strict grounding only             │
                          │  (chỉ dùng retrieved context, không suy diễn)    │
                          └─────────────────────────┬────────────────────────┘
                                                    │
                               ┌────────────────────▼────────────────────┐
                               │            Citation Verifier            │
                               │  Đối chiếu trích dẫn với KB gốc         │
                               │  Đánh dấu "Chưa xác minh" nếu lệch      │
                               └────────────────────┬────────────────────┘
                                                    │
                               ┌────────────────────▼────────────────────┐
                               │           Disclaimer Injector           │
                               │  Chèn disclaimer bắt buộc 100% output   │
                               └────────────────────┬────────────────────┘
                                                    │
                               ┌────────────────────▼────────────────────┐
                               │             Kết quả trả về              │
                               │  Trả lời + Trích dẫn (click-through)    │
                               │  + Disclaimer + Lưu lịch sử & Bookmark  │
                               └─────────────────────────────────────────┘
```

### 4.3 Luồng TO-BE - Alert System & KB Manual Update

```
┌────────────────────────┐     ┌──────────────────────┐     ┌──────────────────────────────────┐
│  ADMIN tải file        │────>│  Parser & Metadata   │────>│  KB Update Queue                 │
│  PDF/Word lên thủ công │     │  Extractor           │     │  (status=pending)                │
└────────────────────────┘     └──────────────────────┘     └────────────────┬─────────────────┘
                                                                             │
                                                            ┌────────────────▼─────────────────┐
                                                            │  ADMIN Duyệt (HITL Review)       │
                                                            │  Approved -> Publish vào pgvector│
                                                            └────────────────┬─────────────────┘
                                                                             │
                                                            ┌────────────────▼─────────────────┐
                                                            │  In-app Notification Engine      │
                                                            │  Tạo alert hiển thị cho USER     │
                                                            └──────────────────────────────────┘
```

### 4.4 Quy tắc Active Filter - Bảng ưu tiên văn bản

| Tình huống | Hành vi hệ thống |
|---|---|
| Văn bản `status=active` | Đưa vào retrieval bình thường |
| Văn bản `status=repealed` | Lọc ra khỏi retrieval; nếu người dùng hỏi trực tiếp về văn bản đó → trả lời "Văn bản X đã hết hiệu lực từ [ngày], thay thế bởi Y" |
| Hai văn bản active mâu thuẫn | Trả về cả hai + cảnh báo mâu thuẫn + quy tắc ưu tiên |
| Văn bản pending review (mới tải lên) | Chưa đưa vào retrieval cho đến khi Admin duyệt |

---

## 5. Data Model sơ bộ

### 5.1 Các Entity chính

```
┌────────────────────┐     ┌────────────────────┐     ┌───────────────────┐
│   LegalDocument    │     │  DocumentChunk     │     │  User             │
├────────────────────┤     ├────────────────────┤     ├───────────────────┤
│ doc_id PK          │◄───┐│ chunk_id PK        │     │ user_id PK        │
│ title              │    ││ doc_id FK          │     │ username          │
│ doc_type           │    ││ text               │    ┌│ password_hash     │
│ status             │    ││ chunk_type         │    ││ role (USER|ADMIN) │
│  (active|repealed) │    ││  (dieu|khoan|diem) │    ││ email             │
│ effective_date     │    ││ chapter_num        │    ││ is_active         │
│ expiry_date        │    ││ article_num        │    │└───────────────────┘
│ replaced_by_id FK  │    ││ clause_num         │    │
│ source_url         │    ││ point_num          │    │ ┌───────────────────┐
│ issuer             │    ││ embedding_vector   │    │ │   QASession       │
│ domain[]           │    ││ metadata_json      │    │ ├───────────────────┤
└────────────────────┘    │└────────────────────┘    └─│ session_id PK     │
                          │                            │ user_id FK        │
                          │ ┌────────────────────┐     │ title             │
                          │ │  QAMessage         │     │ is_bookmarked     │
                          │ ├────────────────────┤     │ bookmark_title    │
                          │ │ msg_id PK          │     │ bookmarked_at     │
                          │ │ session_id FK      │     └───────────────────┘
                          └─│citations[doc_id FK]│
                            │role: user/assistant│
                            │ content            │      ┌───────────────────┐
                            │ faithfulness_score │      │ InAppNotification │
                            │ disclaimer_shown   │      ├───────────────────┤
                            │ latency_ms         │      │ notification_id PK│
                            └────────────────────┘      │ doc_id FK         │
                                                        │ title             │
┌────────────────────┐                                  │ summary           │
│  KBUpdateQueue     │                                  │ created_at        │
├────────────────────┤                                  └───────────────────┘
│ update_id PK       │
│ doc_id FK          │
│ action             │
│ submitted_at       │
│ reviewed_by FK     │
│ status             │
│  (pending|approved │
│   |rejected)       │
└────────────────────┘
```

### 5.2 Quy tắc Metadata bắt buộc

- Mọi `DocumentChunk` phải inherit `status`, `effective_date`, `expiry_date` từ `LegalDocument` cha.
- Khi `LegalDocument` chuyển sang `status=repealed`, TOÀN BỘ chunk liên kết phải được cập nhật đồng thời - không cho phép orphan chunks active.
- `replaced_by_id` là quan hệ thay thế toàn văn tùy chọn. Trường hợp bãi bỏ/sửa đổi một phần hoặc có nhiều nguồn kế tiếp phải dùng `document_relations`; không ép một UUID đại diện cho mọi nhóm nội dung.
- Pipeline indexing phải validate: mỗi chunk có `embedding_vector` và `metadata_json` đầy đủ trước khi push vào PostgreSQL (lưu trực tiếp vector bằng pgvector).
- Kỹ thuật **Parent-Child Chunking**: Nội dung chunk phải được làm giàu ngữ cảnh (Context Enrichment) với format `[Tên Văn Bản] - [Chương] - [Điều] - [Khoản]: [Nội dung]` để tránh Context Fragmentation.
- `KBUpdateQueue.status=pending` → chunk tương ứng KHÔNG được đưa vào retrieval cho đến khi Admin duyệt (`status=approved`).

---

## 6. Phân kỳ triển khai MVP

| Phase | Nội dung | Output |
|---|---|---|
| **Phase 0 - Foundation** | Setup infra (FastAPI + PostgreSQL pgvector + Redis). Auth & RBAC (USER/ADMIN). CI/CD pipeline. Evaluation framework có kết quả `passed` / `failed` / `invalid`, không quy lỗi evaluator hoặc case bị bỏ qua thành điểm đạt. | Backend skeleton hoạt động. Release gate có coverage, case diagnostics và lưu lịch sử vào PostgreSQL. |
| **Phase 1 - KB Core** | ADMIN tải file thủ công (PDF/Word). Custom parser bảo toàn Điều-Khoản-Điểm với **Parent-Child Chunking**. Áp dụng filter metadata trên PostgreSQL để chặn các văn bản Repealed. | KB với các văn bản. Faithfulness ≥ 80% trên golden dataset. |
| **Phase 2 - RAG Q&A** | Hybrid Retriever. LLM Generator (GPT-4o-mini) với strict grounding. Citation Verifier. Disclaimer Injector. Chat UI (web responsive), bookmarks & history cho USER. Out-of-scope filter bằng **Intent Classifier**. | Q&A chat hoạt động end-to-end. P95 < 5s. Hallucination Rate < 8%. |
| **Phase 3 - Admin Dashboard & Alerts** | In-app Alert System realtime (Thông báo luật mới cho USER qua SSE). Admin Dashboard (phê duyệt HITL, quản lý tài khoản người dùng, xem dashboard giám sát AI quality). | Quản lý người dùng, duyệt KB hoạt động. USER nhận thông báo in-app ngay khi ADMIN approve văn bản. |
| **Phase 4 - Polish + Pilot** | UAT với nhóm người dùng thử nghiệm. Bug fix, fine-tune. UX improvement từ feedback thực tế. Tuning metadata filter, reranker. Load test. | Hệ thống ổn định. Faithfulness trung bình ≥ 92%, từng case ≥ 80%, full execution/coverage; NPS ≥ 7/10. |
| **Phase 5 - Go-to-Market** | Mở rộng KB (Thông tư địa phương, quy định ngành). Xem xét các gói dịch vụ B2C & B2B. | Sản phẩm thương mại hóa. |

---

## Tính năng sáng tạo

| # | Tính năng sáng tạo | Vì sao cần? |
|---|---|---|
| 1 | **"Như thế này có bị phạt không?" - Quick Compliance Check** | USER mô tả tình huống bằng ngôn ngữ thường ngày: *"tài xế nghỉ 30 phút sau 4 tiếng rưỡi lái xe liên tục có sao không?"* - hệ thống tự phân tích, trả lời Có/Không + giải thích rõ ràng theo đúng Điều-Khoản thay vì buộc người dùng phải biết đặt câu hỏi pháp lý đúng chuẩn. |
| 2 | **Conflict Resolver - Tư vấn ưu tiên Văn bản Mâu thuẫn (Phase 2+)** | Khi câu hỏi liên quan đến quy định chồng chéo (VD: Luật 118/2025 vs Bộ luật Lao động 2019), hệ thống giải thích quy tắc ưu tiên, khuyến nghị thực hành an toàn nhất thay vì bắt người dùng tự chọn. |
| 3 | **KB Version Diff - So sánh Luật cũ vs Luật mới** | USER muốn biết quy định trong NĐ 100 hiện được điều chỉnh ở nguồn nào. Hệ thống chọn NĐ 168 hoặc NĐ 336 theo chủ đề rồi hiển thị điều khoản thay đổi, tránh so sánh sai phạm vi. |
| 4 | **Escalation CTA - Gợi ý Hỏi Luật sư đúng lúc** | Hệ thống nhận diện khi câu hỏi có độ phức tạp cao (đa văn bản, mâu thuẫn pháp lý, liên quan đến tranh chấp...) và chủ động hiển thị gợi ý liên hệ văn phòng luật sư chuyên ngành GTVT để tăng độ tin cậy và chuyên nghiệp. |

---

**Kết luận Bước 2:**  
Tài liệu PRD này đã chi tiết hóa toàn bộ yêu cầu từ **User Stories** (2 nhóm người dùng USER và ADMIN, 11 stories) và **Functional Requirements** (8 core + 4 nice-to-have).
