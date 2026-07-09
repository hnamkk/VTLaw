# Worklog - AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải

> Ghi theo tuần/mốc sản phẩm. Chỉ giữ các đầu việc có ảnh hưởng rõ đến sản phẩm; các fix nhỏ được gộp vào mốc liên quan. Bằng chứng bám theo `git log`, README và `docs/project/`. Timeline chỉ ghi đến commit mới nhất hiện có trong git log: 09/07/2026.

---

## 20/06 - 23/06/2026: Nền tảng kiểm duyệt Knowledge Base

| Hạng mục | Trạng thái | Kết quả chính | Bằng chứng |
|---|---|---|---|
| KB review workflow | Hoàn thành | Hoàn thiện luồng duyệt tài liệu, upload KB và tài liệu hướng dẫn ban đầu | `004b0b1`, PR #16 |
| Bảo mật và retrieval cho KB | Hoàn thành | Siết upload, tham số full-text search, quyền review và điều kiện retrieval | `8001f6f`, `d29408d` |

**Tóm tắt:** Giai đoạn này đặt nền cho nguyên tắc quan trọng của dự án: dữ liệu pháp lý phải đi qua luồng kiểm duyệt trước khi được dùng trong public search/chatbot.

---

## 24/06 - 30/06/2026: Public access, deploy và chatbot RAG

| Hạng mục | Trạng thái | Kết quả chính | Bằng chứng |
|---|---|---|---|
| Public document/search flow | Hoàn thành | Người dùng có thể tiếp cận tài liệu public; luồng approval async ổn định hơn | `a93080b`, `3506970` |
| Auth và responsive UX | Hoàn thành | Bổ sung public auth, kiểm tra bảo mật auth và giao diện responsive | `d0f88a6`, `ee1a881` |
| Vercel/Railway deployment | Hoàn thành | Chuẩn bị cấu hình deploy, healthcheck, migration và dependency cho Railway/Vercel | `7ec7683`, `0429997`, `b941691`, `32dd8d5` |
| Object storage cho upload | Hoàn thành | Thêm hỗ trợ S3-compatible storage để chuẩn bị lưu file bền vững hơn khi deploy | `56d159b` |
| Chat streaming, session và guardrail | Hoàn thành | Củng cố session ownership, streaming persistence, lịch sử hội thoại và guardrail | `4c8e172`, `84586b6`, PR #25 |
| AI quality operations | Hoàn thành | Bổ sung luồng evidence/quality để theo dõi chất lượng AI | `c2429a9`, `e6d96e5`, PR #27 |
| RAG pipeline hardening | Hoàn thành | Siết retrieval routing, verification, session safety và chatbot RAG pipeline | `4f11314`, `9d51fa3`, `3ac27cc`, `3f587c5`, PR #29 |

**Tóm tắt:** Đây là giai đoạn biến chatbot từ bản có thể hỏi đáp thành hệ thống có thể vận hành: có auth, public access, deployment path, session/history, guardrail và retrieval verification.

---

## 01/07 - 09/07/2026: KB v2, quyết định nghiệp vụ và release gate

| Hạng mục | Trạng thái | Kết quả chính | Bằng chứng |
|---|---|---|---|
| Tài liệu demo | Hoàn thành | README giữ link MVP, Demo, Slide, Thumbnail phục vụ trình bày sản phẩm | `b336350` |
| KB v2 workflow/UI | Hoàn thành | Checkpoint KB v2, cải thiện UI review, relation actions, search paging và publish workflow | `5218d13`, `801ff40`, `7a692c0`, PR #30 |
| Chatbot production behavior | Hoàn thành | Hoàn thiện citation, metadata contract, guardrail, follow-up/history và historical reference isolation | `d86c77e`, PR #31 |
| Dọn artifact sinh tự động | Hoàn thành | Ngừng track artifact generated không cần đưa vào repository | `5258801` |
| Golden dataset và eval gate | Hoàn thành | Full eval 145/145 cases executed/valid, release gate `PASS` | [docs/project/14-rag-evaluation-dataset.md](docs/project/14-rag-evaluation-dataset.md) |

**Tóm tắt:** Giai đoạn này chốt logic nghiệp vụ cốt lõi: chatbot chỉ dùng KB v2 active/published, citation có cấu trúc, tách nguồn tổng quan với Điều/Khoản, tách citation lịch sử khỏi căn cứ hiện hành, có risk metadata và guardrail cho out-of-scope/prompt injection/legal strategy.

### Chỉ số release gate hiện tại

| Nhóm kiểm tra | Kết quả |
|---|---:|
| Golden dataset | 145 cases |
| Full run | 145 executed / 145 valid |
| Release gate | PASS |
| Faithfulness | 1.00 |
| Citation accuracy | 100% |
| Required provision citation coverage | 100% |
| Required document source coverage | 100% |
| Metadata contract completeness | 100% |
| Out-of-scope / prompt injection / legal strategy guardrail | 100% |
| Historical reference isolation | 100% |
| Active-filter violations | 0 |
| Disclaimer missing | 0 |
| High-risk unsupported claims | 0 |
| P95 latency | Khoảng 4.0-4.5s theo eval docs |
| Answer relevancy | 0.76, warning-only |

---

## Ghi chú theo dõi

> Phần này không phải timeline git log, chỉ là các việc cần kiểm tra khi vận hành/deploy lại.

| Việc cần theo dõi | Mức độ | Ghi chú |
|---|---|---|
| Railway DB có đúng corpus KB v2 25 văn bản hay chưa | Cao | Kết nối DB thành công chưa đủ; cần kiểm tra bảng KB v2, revision, retrieval units và trạng thái published/active |
| Vercel gọi đúng backend Railway | Cao | `NEXT_PUBLIC_API_URL` phải trỏ về domain backend production, không dùng localhost |
| Object storage cho source files | Trung bình | Cần bật nếu muốn file upload/source download bền vững qua redeploy |
| Answer relevancy | Theo dõi | Hiện là warning-only; không nên hạ chuẩn citation/guardrail để đổi lấy câu trả lời dài hơn |
