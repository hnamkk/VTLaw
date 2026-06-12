# RAG Chunking Specification
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

**Ngày tạo:** 11/06/2026  
**Phiên bản:** v1.0  
**Liên quan:** PRD F01, F02, F03, F04; Database `legal_documents`, `document_chunks`

---

## 1. Mục tiêu

Tài liệu này đặc tả cách parser và chunker chuyển văn bản pháp luật PDF/DOCX thành các chunk phục vụ RAG. Mục tiêu là giữ nguyên cấu trúc pháp lý Chương -> Điều -> Khoản -> Điểm, hỗ trợ citation chính xác và đảm bảo metadata hiệu lực được lọc trước retrieval.

## 2. Input / Output

| Thành phần | Mô tả |
|---|---|
| Input | File PDF/DOCX do ADMIN upload, metadata ban đầu, source URL |
| Output | Bản ghi `legal_documents`, danh sách `document_chunks`, embedding vector, parser warnings |
| Người duyệt | ADMIN trong HITL Review |
| Điều kiện publish | Metadata bắt buộc hợp lệ, không có chunk rỗng, source URL đã kiểm tra |

> Ingestion KB hiện parse DOCX thành `kb_v2_canonical_nodes`, duyệt qua HITL rồi
> tạo retrieval units khi công bố. Node rủi ro (`table`, `form`, `appendix`,
> `image_caption`) mang quyết định `answerable` hoặc `review_only`; metadata
> `container_type`, `container_label`, `in_appendix` được giữ để UI và tác vụ
> bảo trì áp dụng cùng một quy tắc.

## 3. Metadata bắt buộc

### 3.1 Metadata cấp văn bản

| Field | Bắt buộc | Ví dụ | Ghi chú |
|---|---:|---|---|
| `doc_id` | Có | UUID | Sinh khi upload |
| `title` | Có | NĐ 336/2025/NĐ-CP | Tên văn bản hiển thị |
| `doc_type` | Có | NGHI_DINH | LUAT, NGHI_DINH, THONG_TU, CONG_VAN |
| `issuer` | Có | Chính phủ | Cơ quan ban hành |
| `status` | Có | active | active, repealed, pending_review |
| `effective_date` | Có | 01/03/2026 | Ngày bắt đầu hiệu lực |
| `expiry_date` | Không | null | Có nếu hết hiệu lực |
| `replaced_by_id` | Không | UUID | Văn bản thay thế |
| `source_url` | Có | vbpl.vn/... | Nguồn chính thức hoặc nguồn nội bộ đã xác minh |
| `domain_tags` | Có | xe_tai, xu_phat | Dùng filter phụ |

### 3.2 Metadata cấp chunk

| Field | Bắt buộc | Ví dụ | Ghi chú |
|---|---:|---|---|
| `chunk_id` | Có | UUID | ID citation chính |
| `doc_id` | Có | UUID | FK tới `legal_documents` |
| `chunk_type` | Có | khoan | chuong, dieu, khoan, diem, phu_luc |
| `chapter_num` | Không | 2 | Nullable |
| `article_num` | Có với chunk pháp lý | 9 | Số Điều |
| `clause_num` | Không | 1 | Số Khoản |
| `point_num` | Không | a | Điểm a/b/c |
| `status` | Có | active | Denormalized từ văn bản |
| `effective_date` | Có | 01/03/2026 | Denormalized từ văn bản |
| `metadata_json` | Có | JSONB | Lưu heading path, source page, parser confidence |

## 4. Chiến lược chunking

| Cấp | Khi nào tạo chunk | Nội dung chunk |
|---|---|---|
| Chương | Chỉ khi Chương có phần mô tả riêng | Heading + mô tả chương |
| Điều | Canonical tree luôn có một node cha cho mỗi `article_num`; nếu chunker bỏ heading không có thân riêng thì parser tạo node `structural_only`, `answerable=false` | Tiêu đề Điều hoặc nội dung tổng quát của Điều |
| Khoản | Cấp chunk chính cho retrieval | Heading path + nội dung Khoản |
| Điểm | Tạo khi Điểm dài hoặc chứa quy định riêng | Heading path + nội dung Điểm |
| Phụ lục/Bảng | Tạo theo hàng/nhóm hàng logic | Caption + hàng liên quan + ghi chú |

## 5. Parent-child chunking

Mỗi chunk nhỏ phải được làm giàu ngữ cảnh khi embedding để tránh mất nghĩa.

| Trường | Nội dung |
|---|---|
| `text_content` | Nội dung gốc dùng hiển thị và citation |
| `embedding_content` | Chuỗi giàu ngữ cảnh dùng tạo embedding |
| `display_path` | Tên văn bản -> Chương -> Điều -> Khoản -> Điểm |
| `source_order` | Thứ tự xuất hiện tuyệt đối của chunk trong file nguồn; màn review và các tác vụ kiểm tra chunk phải ưu tiên trường này thay vì tự sắp theo số Điều/Khoản |
| `content_kind` | `legal_text`, `preamble`, `table` hoặc `structure`; `structure` chỉ giữ cây Điều và không tạo retrieval unit |

Format `embedding_content`:

```text
[Tên văn bản] | [Loại văn bản] | [Ngày hiệu lực] | [Trạng thái]
[Chương X: Tên chương]
[Điều Y: Tên điều]
[Khoản Z / Điểm a]
[Nội dung gốc]
```

## 6. Quy tắc xử lý PDF/DOCX

> **Ưu tiên định dạng DOCX cho MVP.** File Word giữ nguyên DOM của bảng (`document.tables` trong python-docx), cho phép map chính xác từng hàng với tiêu đề cột — quan trọng với bảng mức phạt thường kéo dài qua nhiều trang. PDF (pdfplumber) dễ mất tiêu đề cột khi bảng vắt qua page break, nên chỉ xử lý best-effort; khuyến nghị ADMIN upload bản DOCX gốc từ thư viện pháp luật.

Parser chuẩn hóa Unicode NFC, khoảng trắng không ngắt dòng, ký tự zero-width và soft hyphen.
Việc làm sạch chỉ loại artifact kỹ thuật, không tự sửa chính tả hoặc viết lại nội dung pháp lý.
Phần nội dung trước Chương/Điều đầu tiên được giữ dưới dạng `content_kind=preamble`.
Trong KB v2, các khối hành chính như `quoc hieu/tieu ngu`, `thong tin ban hanh`,
`nguoi ky`, `noi nhan` duoc nhan dien them o lop canonical node va danh dau
`review_only`, khong dua vao answerable retrieval mac dinh.
KB parser theo dõi context `appendix` ở cấp canonical node. Chỉ draft cấp
`phu_luc` có heading `Phụ lục`, `Mẫu số`, `Biểu mẫu` hoặc `Danh mục` mới mở vùng
phụ lục; câu nhắc “Phụ lục I” bên trong một Khoản không được phép chuyển vùng.
Sau khi vào vùng phụ lục, các marker Điều/Khoản của biểu mẫu đều là nội dung đối
chiếu, không được tạo node pháp lý dùng cho hỏi đáp.
Đối với văn bản hợp nhất, các chú thích nguồn và danh sách văn bản sửa đổi thường
được đánh số `1.`, `2.` hoặc `a)` trước Điều đầu tiên. Các dòng này vẫn thuộc
`preamble`, được giữ nguyên cả ký hiệu đánh số và không được suy diễn thành
Khoản/Điểm khi chưa có ngữ cảnh Điều.
Chu thich/editorial note cuoi trang hoac cuoi van ban dang `[1] ...`, `Chu thich:`,
`Ghi chu:` hoac `Nguon:` duoc giu trong canonical tree de audit/view, nhung duoc
danh dau `review_only` va khong tao retrieval unit answerable.
Với bảng DOCX, ô merge bị lặp do XML grid được loại trùng liền kề trước khi lưu.

| Trường hợp | Quy tắc |
|---|---|
| OCR confidence thấp | Gắn warning, bắt buộc ADMIN kiểm tra trong HITL |
| Header/footer lặp lại | Loại khỏi `text_content`, lưu page number trong metadata |
| Bảng mức phạt | Giữ theo hàng, không tách khỏi tiêu đề cột |
| Văn bản sửa đổi/bổ sung | Gắn `amends_doc_id`, `amended_article_num` nếu nhận diện được |
| Điều bị bãi bỏ | Tạo chunk trạng thái repealed hoặc note trong metadata, không active retrieval |
| Chunk quá ngắn | Giữ nguyên nếu có locator pháp lý riêng; không merge qua ranh giới Điều/Khoản/Điểm |
| Chunk quá dài | Split theo Khoản/Điểm, giữ heading path cho từng phần |

Trước khi gọi embedding, ingestion kiểm tra lại invariant hierarchy tương ứng
với constraint DB: chunk `dieu`, `khoan`, `diem` bắt buộc có `article_num`.
Draft không hợp lệ bị chặn trước khi tiêu tốn quota embedding và hồ sơ giữ trạng
thái lỗi trong hàng đợi để xử lý lại.

Với chunk pháp lý, `heading_path` (đặc biệt tiêu đề Điều mô tả loại phương tiện
hoặc chủ thể) phải được lưu vào `section_path`. Runtime vẫn fallback sang
`metadata_json.heading_path` để tương thích với các bản index cũ. Heading này
tham gia embedding, local ranking và context gửi LLM; nếu bỏ qua, các khoản có
cùng câu chữ nhưng áp dụng cho xe ô tô, xe mô tô hoặc xe máy chuyên dùng rất dễ
bị nhầm lẫn.

### 6.1 Quy chuẩn kỹ thuật QCVN

QCVN dùng parser profile `qcvn`, không ép vào mô hình Điều/Khoản. Chunk hỗ trợ
`technical_section`, `sign_definition`, `sign_group`, `table` và `figure_caption`;
locator dùng `section_number`, `section_path`, `sign_codes`, `figure_ids` hoặc `table_id`.
Với chunk có nhiều mã biển, `locator_label` chỉ là nhãn ngắn trong giới hạn DB
(`Biển N mã: ...`); danh sách mã đầy đủ phải nằm trong `sign_codes` và
`metadata_json.sign_codes`.
Ảnh được lưu thành asset review-only và không tham gia embedding.

## 7. Ngưỡng MVP

| Tham số | Giá trị đề xuất |
|---|---:|
| Min chunk length | 80 ký tự |
| Max chunk length | 1.500 ký tự |
| Max embedding content | 2.500 ký tự |
| Parser warning threshold | OCR confidence < 0.90 |
| Chunk rỗng | Không được publish |

## 8. Acceptance Criteria

- 100% chunk có `doc_id`, `chunk_id`, `status`, `effective_date`.
- 100% chunk thuộc Điều/Khoản/Điểm có path pháp lý đầy đủ.
- Không publish văn bản nếu còn chunk rỗng hoặc thiếu metadata hiệu lực.
- Citation Viewer phải mở được đúng chunk nguồn từ `chunk_id`.
- Embedding model thống nhất: `text-embedding-3-small`, vector 1536 chiều.
