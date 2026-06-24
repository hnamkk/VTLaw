# Sơ đồ Kiến trúc Hệ thống (Architecture Diagrams)

Tài liệu này chứa các sơ đồ kiến trúc hệ thống và luồng xử lý chi tiết cho dự án **AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải Đường Bộ**. 

> [!NOTE]
> Để xem chi tiết các đặc tả thành phần và thiết kế Cơ sở Dữ liệu, vui lòng tham khảo [docs/project/05-architecture.md](project/05-architecture.md) và [docs/project/06-database-schema.md](project/06-database-schema.md).

---

## 1. Sơ đồ Kiến trúc Tổng quan (System Overview)
Sơ đồ mô tả luồng truyền dữ liệu từ Client (Next.js) qua FastAPI, điều phối bằng LangGraph Agent, truy vấn PostgreSQL + pgvector và tương tác với các mô hình LLM/Embedding/Reranker.

```mermaid
graph TB
    subgraph Frontend [Tầng Trình Diễn - Web UI]
        UI[React/Next.js Client]
        Chat[Chat Interface]
        AdminPanel[Admin Dashboard]
    end

    subgraph Backend [Tầng Nghiệp Vụ - FastAPI Backend]
        API[API Gateway / Routes]
        Auth[Xác thực & Phân quyền JWT]
        Agent[LangGraph Agent Orchestrator]
        Verifier[Citation Verifier]
        Router[Intent Router]
        Parser[Document Parser]
    end

    subgraph Data [Tầng Dữ Liệu - Persistence Layer]
        DB[(PostgreSQL 16 + pgvector)]
    end

    subgraph External [Dịch vụ Bên Ngoài]
        LLM[OpenAI GPT-4o-mini]
        EmbedModel[OpenAI text-embedding-3-small]
        RerankModel[Local Legal Ranker]
    end

    UI -->|HTTPS / JSON / SSE| API
    API --> Auth
    API --> Parser
    API --> Agent
    
    %% Luồng RAG & Agent
    Agent --> Router
    Router -->|1. Hybrid search status=active| DB
    Router -->|2. Rerank chunks| RerankModel
    Router -->|3. Gọi mô hình| LLM
    Agent --> Verifier
    Verifier -->|Đối chiếu nguồn| DB
    
    %% Lưu trữ
    API --> DB
    Parser -->|Trích xuất chunks + metadata| DB
    Parser -->|Tạo embeddings| EmbedModel
    EmbedModel -->|Lưu vector| DB
```

---

## 2. Luồng Trực quan của Agent (LangGraph Flow)
Agent được thiết kế dưới dạng Máy trạng thái (State Machine) bằng LangGraph, có kiểm soát đầu ra nghiêm ngặt để phát hiện và ngăn chặn hallucination (sự suy diễn sai lệch của mô hình ngôn ngữ lớn).

```mermaid
graph TD
    START((Bắt đầu)) --> ParseInput[Parse User Query]
    ParseInput --> FilterScope{"Trong phạm vi<br>Luật Giao Thông?"}
    
    %% Lọc câu hỏi ngoài phạm vi
    FilterScope -->|Không| Deflect["Trả lời Từ Chối<br>Lịch Sự + Gợi ý"]
    Deflect --> END((Kết thúc))
    
    %% Xử lý câu hỏi hợp lệ
    FilterScope -->|Có| ActiveFilter["Metadata Filter:<br>Lọc status = 'active'"]
    ActiveFilter --> Retrieve["Hybrid Retrieval:<br>pgvector + PostgreSQL FTS"]
    Retrieve --> Rerank[Local legal ranking]
    Rerank --> LLMGen["LLM Sinh Phản Hồi<br>Strict Grounding"]
    
    %% Kiểm chứng trích dẫn
    LLMGen --> VerifyCitation{"Verify Citation<br>Khớp với Context?"}
    VerifyCitation -->|Lệch / Sai| MarkUnverified["Đánh dấu 'Chưa xác minh'<br>Cảnh báo nguồn"]
    VerifyCitation -->|Khớp| InjectDisclaimer["Chèn Disclaimer bắt buộc<br>100% Legal output"]
    
    MarkUnverified --> InjectDisclaimer
    InjectDisclaimer --> SaveSession["Lưu Q&A Session<br>vào Database"]
    SaveSession --> END
```

---

## 3. Bản đồ Triển khai (Deployment Topology)
Mô tả cách thức container hóa các dịch vụ trong môi trường phát triển (Local Docker Compose) hoặc khi chạy thực tế trên Cloud (Render & Vercel).

```mermaid
graph LR
    subgraph Client-Side [Trình duyệt Người dùng]
        VercelFE[Vercel: Next.js Responsive Web UI]
    end

    subgraph Production-Cloud [Render / Cloud VPS]
        subgraph Docker-Compose [Docker Compose Environment]
            FastAPI[FastAPI Web Server Container]
            PostgresDB[(PostgreSQL 16 + pgvector Container)]
        end
    end

    subgraph LLM-Cloud [Dịch vụ APIs bên ngoài]
        OpenAI[OpenAI APIs]
        LocalRank[Local legal ranker]
        LangSmith[LangSmith Tracing Server]
    end

    VercelFE -->|REST API & SSE / TLS 1.3| FastAPI
    FastAPI -->|Port 5432| PostgresDB
    FastAPI -->|REST API Call| OpenAI
    FastAPI --> LocalRank
    FastAPI -->|Telemetry Tracing| LangSmith
```
