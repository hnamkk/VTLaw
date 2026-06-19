# Đặc Tả Prompt Và Guardrail
## AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

| Mục | Nội dung |
|---|---|
| Prompt version | `legal-rag-v2` |
| Phạm vi | Chat stream và các nhánh summary động |
| Cập nhật gần nhất | 09/07/2026 |

---

## 1. Mục tiêu

Guardrail phải bảo đảm chatbot:

- chỉ trả lời từ dữ liệu đang công bố
- không suy diễn khi thiếu căn cứ
- không lộ thuật ngữ kỹ thuật ra câu trả lời cho người dùng
- luôn kèm disclaimer cho nội dung pháp lý

---

## 2. Prompt contract

```text
Bạn là trợ lý AI hỗ trợ tra cứu quy định giao thông vận tải đường bộ Việt Nam.
Bạn chỉ được trả lời dựa trên dữ liệu đã được cung cấp từ kho văn bản hiện hành.
Nếu không đủ căn cứ, hãy nói rõ chưa tìm thấy đủ căn cứ trong dữ liệu hiện có.
Mọi khẳng định pháp lý phải nêu rõ văn bản và vị trí căn cứ tương ứng.
Không dùng kiến thức ngoài dữ liệu để tạo thêm căn cứ.
Không tự bịa số hiệu, ngày hiệu lực, mức phạt hoặc điều khoản.
Viết tiếng Việt tự nhiên, dễ hiểu.
```

---

## 3. Dữ liệu đầu vào của prompt

| Biến | Mục đích |
|---|---|
| `user_query` | Câu hỏi gốc |
| `normalized_query` | Query đã chuẩn hóa |
| `query_intent` | Ý định deterministic |
| `retrieved_contexts` | Evidence đã qua filter/ranking |
| `conversation_context` | Dùng để hiểu câu hỏi nối tiếp, không làm căn cứ pháp lý |
| `current_date` | Ngày hệ thống |
| `repealed_notice` | Cảnh báo về vòng đời văn bản nếu cần |

`conversation_context` chỉ được dùng khi follow-up resolver xác định câu hiện tại thật sự phụ thuộc ngữ cảnh và history đủ rõ. Nếu confidence thấp, runtime hỏi lại thay vì cố suy luận topic từ hội thoại cũ.

---

## 4. Guardrail matrix

| Tình huống | Hành vi |
|---|---|
| Ngoài phạm vi | Từ chối lịch sự, gợi ý hỏi lại đúng phạm vi |
| Thiếu căn cứ | Trả template thiếu căn cứ |
| Prompt injection | Chặn trước retrieval/generation |
| Legal strategy cá nhân hóa | Redirect về quy định/thủ tục khách quan; không đưa chiến lược xử lý |
| Yêu cầu bỏ disclaimer | Từ chối |
| Citation không hợp lệ | Chặn output và trả template thiếu căn cứ |
| Văn bản bị tạm ngừng | Không dùng làm căn cứ cho public/chat |
| Hỏi theo số hiệu không tồn tại | Trả lời ngắn gọn là chưa tìm thấy trong kho hiện tại |
| Near-tie nhiều văn bản | Chuyển sang clarification/multiple/insufficient theo evidence policy, không để model tự chọn nguồn chính |

Guardrail input nhận diện thêm các biến thể không dấu và tiếng Anh thường gặp:
`bo qua trich dan`, `bo qua disclaimer`, `bo qua kb`, `answer from memory`,
`do not cite`, `pending review`, `in ra prompt he thong`. Các câu hỏi ngoài
phạm vi rõ như hình sự/ma túy, giá vé máy bay, hộ chiếu/thuế, hoặc luật nước
ngoài như Singapore phải bị deflect trước retrieval, kể cả khi câu có từ khóa
giao thông.

---

## 5. Template thiếu căn cứ

```text
Xin lỗi, tôi chưa tìm thấy đủ căn cứ pháp lý trong dữ liệu hiện có để trả lời chắc chắn câu hỏi này.

Bạn có thể nêu rõ hơn hành vi, loại phương tiện, mốc thời gian hoặc số hiệu văn bản nếu có.

LƯU Ý PHÁP LÝ:
Thông tin này do hệ thống AI tổng hợp, chỉ mang tính tham khảo và không thay thế ý kiến tư vấn pháp lý chuyên nghiệp.
```

## 6. Template ngoài phạm vi

```text
Câu hỏi này nằm ngoài phạm vi tra cứu hiện tại của tôi.

Tôi hiện hỗ trợ tra cứu quy định giao thông đường bộ, vận tải, giấy phép, mức phạt và văn bản liên quan trong kho dữ liệu của hệ thống.
```

---

## 7. Quy tắc câu trả lời

- Không hiển thị marker kỹ thuật, điểm số hay nhãn nội bộ.
- Không dùng thuật ngữ nội bộ như `citation`, `node`, `parser`, `publish`, `review-only` trên UI trả lời cho người dùng.
- Khi trả lời về giới hạn của chatbot hoặc giá trị pháp lý của câu trả lời, dùng tiếng Việt đầy đủ, dễ hiểu.
- Nếu câu trả lời là nội dung pháp lý, disclaimer là bắt buộc.
- Với câu `procedure`, nếu người dùng hỏi kiểu `toi nen lam gi de...`, prompt phải chuyển thành checklist khach quan theo quy định: điều kiện, hồ sơ, cơ quan tiếp nhận, thời hạn, trình tự.
- Với câu chiến lược như `toi nen kien khong`, `lam sao de tranh bi phat`, guardrail input phải short-circuit sang template redirect thay vì cho LLM tự thương lượng ranh giới.

---

## 8. Guardrail runtime

| Stage | Chặn gì |
|---|---|
| `input` | prompt injection, câu hỏi ngoài phạm vi, câu hỏi quá mơ hồ cần làm rõ, legal strategy cá nhân hóa |
| `retrieval` | số hiệu không tồn tại, văn bản chưa đến hiệu lực, văn bản bị tạm ngừng |
| `rerank` | near-tie nhiều văn bản nhưng thiếu dữ kiện, nhiều khả năng theo facts, hoặc evidence khác hướng |
| `output` | thiếu citation, citation không active, hallucination, low confidence |

Node `deflect` là nhánh kết thúc trực tiếp của graph. Vì vậy mọi phản hồi
deflect không phải small-talk phải tự gắn disclaimer nếu template chưa có sẵn,
không phụ thuộc node `inject_disclaimer` ở cuối pipeline.

`POST /api/v1/chat/stream` trả metadata audit trong SSE `done`:

- `guardrail_triggered`
- `guardrail_stage`
- `guardrail_reason`
- `answer_mode`
- `confidence`
- `clarification_question`

Quy ước `answer_mode` hiện hành:

- `direct`: trả lời pháp lý trực tiếp từ evidence hợp lệ
- `summary`: nhánh tóm tắt văn bản
- `historical`: intent hỏi so sánh/lịch sử
- `clarification_needed`: guardrail đầu vào yêu cầu người dùng làm rõ
- `multiple_possibilities`: câu hỏi mang tính chiến lược hoặc còn phụ thuộc dữ kiện, không coi là tư vấn trực tiếp
- `insufficient_evidence`: guardrail đầu ra thiếu căn cứ hoặc citation không hợp lệ
- `out_of_scope`: câu hỏi ngoài phạm vi hoặc prompt injection

Với notice từ evidence policy, prompt generation phải tuân thủ thêm các ràng buộc sau:

- nếu evidence là bổ sung nhiều tầng văn bản thì trình bày vai trò của từng nguồn theo thứ tự `Luat -> Nghi dinh -> Thong tu`
- nếu câu hỏi cụ thể chỉ có con số/căn cứ trực tiếp ở một văn bản thì chỉ dùng văn bản đó cho kết luận chính
- không dùng cụm kết luận như "van ban chinh" khi policy chưa xác định được một nguồn duy nhất

`risk_level` cũng được gán bằng rule deterministic từ intent, guardrail và loại câu hỏi:

- `low`: tra cứu quy định, định nghĩa hoặc summary rõ
- `medium`: thủ tục, historical, clarification hoặc insufficient
- `high`: mức phạt, tranh chấp, khiếu nại/khởi kiện hoặc câu hỏi chiến lược kiểu `Tôi nên làm gì`

`guardrail_reason = legal_advice_boundary` là nhánh redirect cố định cho các câu hỏi chiến lược cá nhân hóa. Nhánh này:

- không đi retrieval/generation
- vẫn trả disclaimer
- vẫn map ra `answer_mode = multiple_possibilities`
- vẫn map ra `risk_level = high`

Các metadata này chỉ phục vụ audit/debug và điều phối UI; không hiển thị như nội dung người dùng.

Với các nhánh deterministic theo số hiệu văn bản:

- `summary`, `document_lookup`, `effective_status` nên đi kèm `document_sources` để UI có nguồn tổng quan của văn bản
- `provision_citations` vẫn chỉ dành cho căn cứ hiện hành; không dùng để chở metadata lịch sử

---

## 9. Temporal behavior

- Câu hỏi lịch sử mơ hồ mà không có mốc thời gian cụ thể có thể bị yêu cầu làm rõ.
- Nếu chỉ tìm thấy văn bản chưa đến hiệu lực tại `query_date`, hệ thống trả thông báo tương ứng thay vì suy diễn.
- Historical citation vẫn có thể mở nguồn để người dùng đối chiếu lại câu trả lời cũ, nhưng không được làm thay đổi tập dữ liệu đang dùng để trả lời mới.

---

## 10. Acceptance criteria

- 100% câu trả lời pháp lý có disclaimer.
- Không có câu trả lời pháp lý nào thoát ra mà không có citation hợp lệ hoặc template thiếu căn cứ.
- Không có dữ liệu `suspended` được dùng cho public/chat.
- Không có thuật ngữ kỹ thuật hoặc lỗi thô lộ ra UI từ nhánh fallback.

## 11. Versioned query policy inputs

- Deterministic text rules used before/around prompting now load from `app/backend/src/rag/policies/query_policy.json`.
- Current versioned groups include:
  - intent phrase hints
  - follow-up prefixes, phrases, and topic hints
  - legal-advice vs objective-procedure patterns
- Startup path `src.main.lifespan()` validates the query-policy loader early so invalid config fails fast before serving traffic.

## 12. Prompt/guardrail cases locked by golden eval

Golden eval dang co case rieng cho:

- follow-up low-confidence -> `clarification_needed`
- legal strategy personalization -> `guardrail_reason=legal_advice_boundary`
- prompt injection doi bo citation va doi bo disclaimer -> `guardrail_reason=prompt_injection`
- near-tie fact-dependent -> `multiple_possibilities`

Nghia la release gate hien tai da theo doi ca metadata guardrail, khong chi theo doi answer text.

## 13. Runtime updates 2026-07-09

- Input guardrail now fail-closes known unsupported requests such as exact BOT fees, visual sign descriptions, drone-road permits, exact overload payloads, pending-review documents, and current-law questions backed only by inactive material.
- Temporal policy distinguishes clear historical lookup from ambiguous historical wording: clear historical topics use `historical_references`, while missing or multiple date milestones trigger clarification.
- Legal-advice strategy, prompt-injection, out-of-scope, insufficient-evidence, and clarification outputs are direct guardrail responses with no citations.
- Response metadata exposes `answer_mode`, `risk_level`, `confidence`, `provision_citations`, `document_sources`, `historical_references`, and `clarification_question` for UI behavior; risk level is not written into the natural-language answer body.
- Evidence direct responses now use natural Vietnamese wording with accents and no internal markers. The user-facing text must not expose `guardrail_reason`, score, node names, or technical fallback labels.
- For near-tie fact-dependent questions, `evidence_multiple_possibilities` asks the user for missing facts and intentionally emits no citation metadata. UI should show this as a clarification/decision-needed state, not as a cited legal conclusion.
- Multi-document overview questions containing role/comparison phrasing such as `tong quan`, `vai tro`, `khac nhau`, or `phan biet` should present document roles instead of forcing clarification when the sources are complementary rather than conflicting.
- Retrieval snippets used in deterministic fallback answers are clipped at word boundaries and expanded for common abbreviations such as `ATKT` and `BVMT`, so unfinished technical fragments should not appear in the UI.
