# Weekly Journal - AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

> Ghi theo tuần/mốc sản phẩm, không ghi chi tiết từng PR nhỏ. Nội dung tập trung vào điều đã học, quyết định sản phẩm, rủi ro và hướng tiếp theo; dữ kiện bám theo `git log`, README và `docs/project/`. Timeline chỉ ghi đến commit mới nhất hiện có trong git log: 09/07/2026.

---

## Tuần 20/06 - 23/06/2026: Đặt nền cho KB đáng tin cậy

### Trọng tâm

Tuần này tập trung vào việc làm cho Knowledge Base có luồng kiểm duyệt rõ hơn. Đây là nền móng để chatbot sau này không lấy dữ liệu chưa duyệt hoặc dữ liệu sai trạng thái vào câu trả lời.

### Điều đã hoàn thành

- Hoàn thiện bước đầu KB review workflow và tài liệu liên quan.
- Siết upload KB, tham số full-text search, security của review và retrieval.
- Tạo tiền đề cho nguyên tắc active/published-only trong chatbot.

### Điều học được

- Với sản phẩm pháp lý, chất lượng câu trả lời bắt đầu từ chất lượng vòng đời dữ liệu, không phải từ prompt.
- Review workflow không chỉ là tính năng admin; nó là guardrail tầng dữ liệu.

### Bằng chứng chính

`004b0b1`, `8001f6f`, `d29408d`, PR #16.

---

## Tuần 24/06 - 30/06/2026: Từ nền tảng sang hệ thống có thể vận hành

### Trọng tâm

Tuần này mở rộng hệ thống theo hướng production-shaped: public access, auth, deploy cloud, object storage, chat streaming, session history và RAG hardening.

### Điều đã hoàn thành

- Bổ sung public document access và luồng approval async.
- Hoàn thiện auth/public user flow và responsive UI.
- Chuẩn bị triển khai Vercel/Railway, gồm cấu hình build, dependency, migration và healthcheck.
- Thêm object storage support cho upload.
- Củng cố chat session, streaming persistence, guardrail và lịch sử hội thoại.
- Siết retrieval routing, verification và chatbot RAG pipeline.
- Bắt đầu hình thành AI quality operations/evidence flow.

### Quyết định đáng chú ý

- Không xem chatbot là một endpoint prompt đơn lẻ; cần có session, retrieval guard, verification và quality evidence.
- Deploy cloud phải được kiểm tra cùng migration/schema/data, vì chatbot phụ thuộc chặt vào DB và KB.
- Object storage được xem là hướng cần có nếu muốn upload/source file ổn định trên production.

### Điều học được

- RAG pháp lý cần nhiều lớp kiểm soát: input guardrail, retrieval filter, metadata, citation verification và output contract.
- Lịch sử hội thoại hữu ích, nhưng phải có điều kiện rõ ràng để không kéo nhầm ngữ cảnh cũ vào kết luận pháp lý.

### Bằng chứng chính

`a93080b`, `3506970`, `d0f88a6`, `ee1a881`, `7ec7683`, `0429997`, `56d159b`, `4c8e172`, `84586b6`, `3ac27cc`, `3f587c5`, PR #25, PR #27, PR #29.

---

## Tuần 01/07 - 09/07/2026: Chốt logic nghiệp vụ và release gate

### Trọng tâm

Tuần này chuyển chatbot sang trạng thái production-readiness: chốt các quyết định nghiệp vụ, harden KB v2 workflow, mở rộng golden dataset và chạy eval theo release gate.

### Điều đã hoàn thành

- Giữ lại/cập nhật các link MVP, Demo, Slide và Thumbnail trong README.
- Checkpoint KB v2 workflow, cải thiện UI review, relation actions, search paging và publish workflow.
- Hoàn thiện hành vi chatbot production: structured citation, metadata contract, guardrail, follow-up/history, historical reference isolation.
- Dọn generated artifacts khỏi repository.
- Chạy full eval 145 cases và đạt release gate `PASS` theo tài liệu eval.

### Quyết định sản phẩm đã chốt

- Chatbot chỉ dùng KB v2 active/published; không fallback sang bảng legacy hoặc corpus khác.
- Citation Điều/Khoản phải sinh từ retrieval unit/verifier, không phụ thuộc LLM tự viết.
- `provision_citations`, `document_sources` và `historical_references` phải tách riêng để UI không nhầm nguồn tổng quan với căn cứ pháp lý hiện hành.
- `risk_level` trả qua API ở field riêng, không viết lẫn vào nội dung trả lời.
- Câu hỏi thủ tục khách quan có thể trả checklist; câu hỏi chiến lược pháp lý phải được giới hạn hoặc từ chối phù hợp.
- Follow-up dùng lịch sử khi đủ ngữ cảnh; nếu độ tin cậy thấp thì hỏi lại thay vì suy đoán.

### Kết quả eval đáng ghi nhận

| Metric | Kết quả |
|---|---:|
| Golden dataset | 145 cases |
| Full run | 145 executed / 145 valid |
| Release gate | PASS |
| Faithfulness | 1.00 |
| Citation accuracy | 100% |
| Required citation/source coverage | 100% |
| Metadata contract completeness | 100% |
| Guardrail cho out-of-scope, prompt injection, legal strategy | 100% |
| Historical reference isolation | 100% |
| Active-filter violations | 0 |
| Disclaimer missing | 0 |
| High-risk unsupported claims | 0 |

### Điều học được

- Golden dataset không chỉ để kiểm tra “trả lời đúng”, mà còn phải kiểm tra contract API, citation, risk metadata, lịch sử hội thoại và guardrail.
- Những lỗi nguy hiểm nhất không phải lúc chatbot không biết, mà là khi chatbot trả lời có vẻ chắc chắn nhưng thiếu citation hoặc dùng nhầm trạng thái hiệu lực.
- Metric `answer relevancy` nên tiếp tục theo dõi, nhưng không được đánh đổi với hard gate về citation, active filter và guardrail.

### Bằng chứng chính

`b336350`, `5218d13`, `801ff40`, `7a692c0`, `5258801`, `d86c77e`, PR #30, PR #31, [docs/project/14-rag-evaluation-dataset.md](docs/project/14-rag-evaluation-dataset.md).

---

## Ghi chú theo dõi

> Phần này không phải timeline git log, chỉ là các việc cần kiểm tra khi vận hành/deploy lại.

- Smoke test production sau redeploy với `/health`, danh sách văn bản và một vài câu hỏi happy path đã pass eval.
- Nếu restore DB lên Railway, kiểm tra lại corpus KB v2 25 văn bản trước khi demo.
- Tiếp tục theo dõi `answer relevancy` và độ mượt ngôn ngữ trả lời, nhưng giữ nguyên hard gate về citation, active filter và guardrail.
