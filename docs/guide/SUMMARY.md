# 📘 AI20K Project Guide — Tóm tắt toàn diện

> **Mục đích**: File này tổng hợp toàn bộ `docs/guide/` để AI assistant đọc nhanh mỗi session mới,
> thay vì phải đọc lại ~300KB tài liệu gốc. Cập nhật cuối: 2026-06-15.

---

## 1. KIẾN TRÚC HỆ THỐNG

### 1.1 Kiến trúc 3 tầng (BẮT BUỘC)

```
Frontend (React/Next.js hoặc Streamlit)
    ↕ HTTP / SSE
Backend (FastAPI) — business logic, auth, rate-limit, logging
    ↕ function call
AI Agent (LangGraph) — state machine, tools, RAG
    ↕
External: LLM API (OpenAI), Search API (Tavily), Vector DB (ChromaDB)
```

**Nguyên tắc**: Agent KHÔNG giao tiếp trực tiếp với Frontend — mọi thứ qua Backend.

### 1.2 Cấu trúc thư mục chuẩn

```
src/
├── agent/          # LangGraph: graph.py, state.py, nodes.py, tools.py
├── api/            # FastAPI: main.py, routes/, deps.py
├── core/           # Config (pydantic-settings), logging
└── models/         # Pydantic schemas (request/response)
tests/
├── unit/           # Test từng function/node
├── integration/    # Test API endpoint + graph flow
└── eval/           # RAGAS, accuracy test (dùng LLM thật)
docs/
├── architecture/   # Mermaid diagrams
└── adr/            # Architecture Decision Records
eval/               # Datasets + evaluation scripts
presentation/       # Demo Day slides
```

**KHÔNG gộp tất cả code vào 1 file.** Tách biệt concerns: agent ≠ api ≠ config ≠ models.

---

## 2. LANGGRAPH — PATTERNS & NGUYÊN TẮC

### 2.1 State (TypedDict)

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]  # PHẢI dùng reducer cho list
    query: str
    search_results: list[str]
    draft: str
    iteration: int  # Đếm vòng lặp, chống infinite loop
```

**Quy tắc**:
- `total=False` → cho phép field chưa có lúc ban đầu
- **PHẢI** dùng `Annotated[list, add_messages]` cho messages (không dùng → bị ghi đè)
- Chỉ lưu những gì cần thiết — YAGNI
- Tên field rõ ràng: `query`, `search_results`, `draft` — KHÔNG `data1`, `data2`

### 2.2 Nodes

```python
# ✅ ĐÚNG: nhận state, trả về dict chỉ chứa field thay đổi
async def search_node(state: AgentState) -> dict:
    results = await search_api(state.get("query", ""))
    return {"search_results": results}

# ❌ SAI: mutate state trực tiếp
def bad_node(state):
    state["query"] = state["query"].lower()  # KHÔNG LÀM
    return state
```

**Quy tắc**:
- Mỗi node **1 trách nhiệm** (Single Responsibility)
- Trả về **chỉ field thay đổi**, không trả toàn bộ state
- Dùng `async def` khi gọi LLM/API/DB
- **Luôn try-except** — node KHÔNG ĐƯỢC crash graph
- Đặt tên mô tả: `analyze_query`, `generate_answer` — KHÔNG `process`, `handle`, `step1`

### 2.3 Edges & Routing

```python
# Direct edge: A → B cố định
graph.add_edge("analyze", "search")

# Conditional edge: rẽ nhánh theo điều kiện
def route(state: AgentState) -> str:
    if state.get("needs_search"):
        return "search"
    return "answer"  # PHẢI có fallback

graph.add_conditional_edges("router", route, {"search": "search", "answer": "answer"})
```

**Quy tắc**:
- Routing function **PHẢI** trả về giá trị có trong map, **PHẢI** có fallback
- Giới hạn vòng lặp bằng `iteration` counter (max 3) — tránh `GraphRecursionError`
- `START` và `END` là sentinel đặc biệt

### 2.4 Tools

```python
from langchain_core.tools import tool

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """Tìm kiếm thông tin trên web.
    
    Args:
        query: Từ khóa tìm kiếm cụ thể
        max_results: Số kết quả (1-10)
    """
    # Implementation...
```

**Quy tắc**:
- **Docstring = prompt cho LLM** — viết rõ ràng, có ví dụ, mô tả khi nào dùng
- **Type hints bắt buộc** — LLM cần biết kiểu để sinh JSON đúng
- **KHÔNG dùng `eval()`** — dùng AST parsing cho calculator
- **KHÔNG trust input từ LLM** — luôn validate
- Error handling: trả message lỗi thay vì raise exception

### 2.5 ReAct Pattern

```
Think → Act (gọi tool) → Observe (nhận kết quả) → lặp lại hoặc trả lời
```

- Dùng `create_react_agent(llm, tools)` cho nhanh
- Hoặc build thủ công: node "agent" ↔ node "tools" với conditional edge
- Loop: `graph.add_edge("tools", "agent")` tạo vòng lặp

### 2.6 RAG Pattern

```
Query → Embed → Vector Search (top-K) → Context + Query → LLM → Response
```

- `chunk_size`: 300-1000, `chunk_overlap`: 50-200
- ChromaDB cho dev, PGVector/Pinecone cho production
- Prompt RAG: "Dựa trên tài liệu sau, trả lời. Nếu không có → nói rõ."

### 2.7 Error Handling — 3 tầng

| Tầng | Cơ chế | Ví dụ |
|------|--------|-------|
| Node | try-except trong mỗi node | Trả `{"error": "..."}` thay vì crash |
| Graph | `RetryPolicy(max_attempts=3)` | Retry khi ConnectionError/TimeoutError |
| Tool | `ToolNode(handle_tool_errors=True)` | Catch lỗi tool, trả message cho agent |

**Nguyên tắc: fail gracefully, never crash.**

---

## 3. FASTAPI — PATTERNS & NGUYÊN TẮC

### 3.1 Cấu trúc API

- Entry point: `uvicorn src.main:app --reload --port 8000`
- Auto-docs: `http://localhost:8000/docs` (Swagger UI)
- Versioning: `/api/v1/...`
- Health check: `GET /health` trả `{"status": "healthy", "version": "..."}`

### 3.2 Pydantic Models (Request/Response)

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_id: str | None = None
    stream: bool = False

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    sources: list[str] = Field(default_factory=list)
```

**Quy tắc**:
- `Field(...)` = required, `Field(default=...)` = optional
- Dùng `Literal` cho enum: `Literal["vi", "en"]`
- Dùng `field_validator` cho custom validation
- `response_model=ChatResponse` trong route decorator

### 3.3 Error Handling

```python
# Global exception handler — KHÔNG leak internal error
@app.exception_handler(Exception)
async def global_handler(request, exc):
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": "Lỗi hệ thống."})
```

- Phân biệt dev vs prod: dev hiển thị chi tiết, prod chỉ generic message
- **KHÔNG BAO GIỜ** expose stack trace/API key trong response

### 3.4 Streaming (SSE)

```python
@app.post("/api/v1/chat/stream")
async def stream(request: ChatRequest):
    async def generate():
        async for event in agent.astream_events(inputs, config, version="v2"):
            if event["event"] == "on_chat_model_stream":
                token = event["data"]["chunk"].content
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### 3.5 Kết nối Agent

- **Lifespan pattern**: khởi tạo agent 1 lần khi app start, lưu vào `app.state`
- **Dependency Injection**: `AgentManager` singleton, lazy init
- CORS: chỉ định domain cụ thể cho production, `*` chỉ cho dev

### 3.6 Middleware

- Logging middleware: log request/response + timing
- Rate limiting: in-memory cho dev, Redis cho prod (30 req/60s)
- CORS: `allow_origins` phải bao gồm frontend URL

---

## 4. CONFIG & ENVIRONMENT

### 4.1 pydantic-settings

```python
class Settings(BaseSettings):
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = "gpt-4o-mini"
    app_env: Literal["development", "staging", "production"] = "development"
    
    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}

settings = Settings()  # Singleton
```

### 4.2 Quy tắc env

- **KHÔNG BAO GIỜ hardcode secrets** — dùng `.env` + `pydantic-settings`
- `.env` trong `.gitignore` — KHÔNG commit
- `.env.example` commit lên Git — chứa placeholder
- Khi thêm env mới: (1) thêm `.env.example`, (2) thêm field Settings, (3) thêm validation

---

## 5. CODE STYLE — PYTHON

### 5.1 BẮT BUỘC

- **Type hints** cho mọi function: `def f(x: str) -> dict:`
- **Docstring** cho public functions
- **Max 30 lines** per function — dài hơn → tách
- **Max 3 parameters** — nhiều hơn → dùng Pydantic model
- **Specific exception** — KHÔNG bare except

### 5.2 Naming

| Type | Convention | Ví dụ |
|------|-----------|-------|
| File | snake_case | `analyze_node.py` |
| Function | snake_case | `analyze_query()` |
| Class | PascalCase | `AgentState` |
| Constant | UPPER_SNAKE | `MAX_RETRIES = 3` |

### 5.3 Import order

```python
# 1. Standard library
import os
from typing import Optional
# 2. Third-party
from fastapi import APIRouter
from langchain_core.tools import tool
# 3. Local
from src.core.config import settings
```

### 5.4 Linting

```bash
ruff check src/ tests/          # Kiểm tra
ruff check --fix src/ tests/    # Auto-fix
ruff format src/ tests/         # Format
```

---

## 6. DEVOPS

### 6.1 Docker

- Multi-stage build: Stage 1 (builder) cài deps → Stage 2 (production) chỉ copy kết quả
- Non-root user (`appuser`) — bảo mật
- HEALTHCHECK directive
- `.dockerignore`: loại `.env`, `.git`, `.venv`, `__pycache__`, `tests/`
- **KHÔNG lưu secrets trong image** — truyền qua env vars lúc runtime
- Tag image version cụ thể (KHÔNG chỉ `latest`)

### 6.2 Docker Compose

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    depends_on:
      db: {condition: service_healthy}
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    deploy:
      resources:
        limits: {memory: 512M, cpus: "0.5"}
  db:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d db"]
```

- `depends_on` + `condition: service_healthy` → đợi DB ready
- Named volumes cho data persistence
- Resource limits chống memory leak

### 6.3 CI/CD (GitHub Actions) — BẮT BUỘC

```yaml
# .github/workflows/ci.yml
on:
  push: {branches: [main, develop]}
  pull_request: {branches: [main]}
jobs:
  lint:   # ruff check + ruff format --check
  test:   # pytest --cov=app --cov-fail-under=60
  build:  # docker build
```

**Đây là tiêu chí DevOps quan trọng nhất** — 0/12 teams Cohort 1 có CI/CD.

### 6.4 Deploy

- Backend: **Render** hoặc Railway (free tier OK)
- Frontend: **Vercel**
- Free tier Render sleep sau 15 phút → dùng UptimeRobot ping mỗi 5 phút
- Env vars thiết lập trên Render Dashboard

### 6.5 Monitoring & Logging

- **Structured logging** (JSON format) — dùng `JSONFormatter` custom
- **LangSmith** cho AI tracing: chỉ cần 3 env vars (`LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGCHAIN_TRACING_V2=true`)
- Health check endpoint kiểm tra DB, LLM API
- Giảm log noisy: `httpx`, `httpcore`, `urllib3` → WARNING

---

## 7. TESTING

### 7.1 Kim tự tháp test

| Loại | Tỷ lệ | Mock LLM? | Ví dụ |
|------|--------|-----------|-------|
| Unit | 70-80% | Có | Test từng node, routing function |
| Integration | 15-20% | Có | Test API endpoint, graph flow |
| Evaluation | 5-10% | Không | RAGAS metrics, accuracy |

### 7.2 Patterns

```python
# conftest.py — AsyncClient fixture
@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

# Test API
@pytest.mark.asyncio
async def test_chat(client):
    response = await client.post("/api/v1/chat", json={"message": "Hi"})
    assert response.status_code == 200

# Test routing — parametrize
@pytest.mark.parametrize("intent,expected", [("search", "search"), ("greeting", "respond")])
def test_routing(intent, expected):
    assert route_function({"intent": intent}) == expected
```

### 7.3 Quy tắc

- **Mock LLM** trong unit/integration test — KHÔNG gọi API thật (tốn tiền, không ổn định)
- Coverage target: **60%+ tổng thể**, 80%+ cho API, 90%+ cho routing
- Cấu hình `pyproject.toml`: `addopts = "-v --cov=app --cov-fail-under=60"`
- RAGAS: chạy riêng, KHÔNG trong CI (tốn token, chậm)

### 7.4 RAGAS Metrics

| Metric | Đo lường | Target |
|--------|----------|--------|
| Faithfulness | Câu trả lời dựa vào context? | > 0.7 |
| Answer Relevance | Liên quan đến câu hỏi? | > 0.7 |
| Context Precision | Top-K docs đúng thứ tự? | > 0.6 |
| Context Recall | Retrieve đủ docs? | > 0.6 |

---

## 8. GIT WORKFLOW

- **Branching**: `main` (stable) ← `develop` ← `feature/xxx`
- **KHÔNG push trực tiếp lên main** — qua PR
- **Commit message**: `type(scope): mô tả`
  - Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
  - Scope: `agent`, `api`, `config`, `models`, `tests`
- PR: nhỏ, tập trung 1 vấn đề, review bởi ≥1 người
- Commit đều đặn hàng ngày — KHÔNG 5 commits ngày cuối

---

## 9. DELIVERABLES (10 MỤC — BẮT BUỘC)

| # | Deliverable | Trạng thái phổ biến | Lưu ý |
|---|------------|---------------------|-------|
| 1 | Source Code | Phần lớn có | Chạy được sau khi set env |
| 2 | README.md | Phần lớn có | Screenshot, install guide, API docs |
| 3 | Architecture Diagram | Thường thiếu | Mermaid hoặc draw.io |
| 4 | AI Logs | Phần lớn có | LangSmith (3 env vars) |
| 5 | Live URL | Thường có | Render free tier OK |
| 6 | Video Demo | Hiếm | 3-5 phút, YouTube, lợi thế lớn |
| 7 | Pitch Deck | Thường thiếu | 10 slides PDF |
| 8 | Dev Journal | Phần lớn có | 2-3 câu/ngày |
| 9 | Worklog | Phần lớn có | `git log --oneline` |
| 10 | Evaluation Evidence | Hiếm | RAGAS + pytest, lợi thế lớn |

**Nộp đủ 10/10 = vượt phần lớn đội khác** (trung bình chỉ 5/10).

---

## 10. TIÊU CHÍ CHẤM ĐIỂM (5 × 10 = 50 điểm)

| Tiêu chí | 20% | Ghi điểm cao |
|----------|-----|-------------|
| Product/Business | Giá trị SP | Problem statement rõ, demo use case thực |
| System Design | Kiến trúc | Diagram + ADR + giải thích tech choices |
| UI/UX | Giao diện | Responsive, loading states, error messages |
| **DevOps** | Docker/CI/CD | **Dễ ghi điểm nhất** — đa số đội bỏ qua |
| Code Quality | Tests/style | Type hints, tests 60%+, no bare except |

**Chiến lược**: Đảm bảo 7+ ở mọi tiêu chí trước, rồi đẩy 1-2 lên 9+.

---

## 11. ANTI-PATTERNS — SAI SÓT TỪ COHORT 1

### Top 10 lỗi phổ biến (phân tích 12 teams)

1. **Bare except** (3/12) — `except: pass` che lỗi → dùng specific exception + log
2. **Hardcoded secrets** (1/12) — API key trong code → dùng `.env`
3. **Không có tests** (10/12) — 0% coverage → mục tiêu 60%+
4. **Không có CI/CD** (12/12) — 0 teams → GitHub Actions bắt buộc
5. **Functions quá dài** — 200+ lines → max 30 lines/function
6. **Không có Architecture Diagram** (5/12) — mất 2-3 điểm System Design
7. **README kém** (6/12) — thiếu screenshot, install guide
8. **Không có Evaluation Evidence** (10/12) — cơ hội ghi điểm lớn
9. **Tất cả code 1 file** (4/12) — main.py 500+ lines → tách module
10. **Không type hints** — mất 1-2 điểm Code Quality

### Điểm yếu chung: DevOps + Code Quality = điểm thấp nhất

---

## 12. TROUBLESHOOTING NHANH

| Lỗi | Nguyên nhân | Fix |
|-----|-------------|-----|
| `ModuleNotFoundError` | Chưa activate venv | `source .venv/bin/activate` |
| `GraphRecursionError` | Loop vô hạn | Thêm iteration counter, max 3 |
| Routing TypeError | Return không khớp map | Luôn có fallback trong routing |
| Port 8000 bị chiếm | Process cũ | `lsof -i :8000` → `kill -9 <PID>` |
| `AuthenticationError` | API key sai/thiếu | Kiểm tra `.env`, grep OPENAI_API_KEY |
| Docker build fail | Network/deps | `docker build --no-cache .` |
| CORS 403 | Thiếu origin | Thêm frontend URL vào `allow_origins` |
| Render sleep | Free tier | UptimeRobot ping mỗi 5 phút |
| `pydantic.ValidationError` | Env var sai kiểu | Kiểm tra `.env`: port=số, bool=true/false |

---

## 13. ARCHITECTURE DECISION RECORDS (ADR)

### Template

```markdown
# ADR-00X: [Tiêu đề]
**Ngày:** YYYY-MM-DD | **Trạng thái:** Accepted

## Bối cảnh
Vấn đề cần quyết định.

## Lựa chọn
1. Option A — ưu/nhược
2. Option B — ưu/nhược

## Quyết định
Chọn Option X.

## Lý do
1-3 lý do ngắn gọn.

## Hệ quả
Ảnh hưởng của quyết định.
```

Ghi ADR cho: framework, database, LLM provider, deployment, architecture pattern.

---

## 14. FRONTEND NOTES

### Streamlit (prototype nhanh)
- Setup: `pip install streamlit requests` → `streamlit run app.py`
- 30 phút có giao diện chat, OK cho Demo Day
- KHÔNG phù hợp production

### Next.js (production)
- App Router, TypeScript, Tailwind CSS
- `"use client"` directive cho interactive components
- SSE streaming: `fetch` + `ReadableStream`
- Dark mode: `next-themes` + Tailwind `dark:` prefix
- Mobile-first: Tailwind breakpoints (`md:`, `lg:`)

---

## 15. CHECKLIST TRƯỚC KHI PUSH/DEPLOY

- [ ] `ruff check src/ tests/` pass
- [ ] `pytest tests/ -v --cov=app --cov-fail-under=60` pass
- [ ] Không hardcoded secrets trong code
- [ ] Không bare except
- [ ] Type hints cho mọi function
- [ ] `.env` trong `.gitignore`
- [ ] Health check endpoint hoạt động
- [ ] Docker build thành công
- [ ] README có screenshot + install guide
- [ ] Architecture diagram cập nhật
