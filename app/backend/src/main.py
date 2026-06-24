import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from os import getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.admin_assets import router as admin_assets_router
from src.api.v1.admin_kb_v2 import router as admin_kb_v2_router
from src.api.v1.admin_quality import router as admin_quality_router
from src.api.v1.admin_users import router as admin_users_router
from src.api.v1.auth import router as auth_router
from src.api.v1.chat import router as chat_v1_router
from src.api.v1.documents import router as docs_router
from src.api.v1.notifications import router as notifications_router
from src.api.v1.traffic_signs import router as traffic_signs_router
from src.core.config import settings
from src.db.session import async_session_factory
from src.kb.lifecycle import current_legal_date, reconcile_expired_documents
from src.rag.query_policy import validate_query_policy_startup

logger = logging.getLogger(__name__)


async def _document_lifecycle_loop() -> None:
    while True:
        try:
            async with async_session_factory() as session:
                changed = await reconcile_expired_documents(
                    session,
                    as_of=current_legal_date(),
                    source="scheduler",
                )
                await session.commit()
                if changed:
                    logger.info("Archived %s expired legal documents", len(changed))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Document lifecycle reconciliation failed")
        await asyncio.sleep(max(60, settings.DOCUMENT_LIFECYCLE_SYNC_INTERVAL_SECONDS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting LegalAI in {settings.APP_ENV} mode")
    validate_query_policy_startup()
    lifecycle_task = None
    if settings.DOCUMENT_LIFECYCLE_SYNC_ENABLED:
        lifecycle_task = asyncio.create_task(_document_lifecycle_loop())
    yield
    if lifecycle_task is not None:
        lifecycle_task.cancel()
        with suppress(asyncio.CancelledError):
            await lifecycle_task
    print("Shutting down...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(chat_v1_router, prefix="/api/v1")
app.include_router(docs_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(admin_kb_v2_router, prefix="/api/v1")
app.include_router(admin_assets_router, prefix="/api/v1")
app.include_router(admin_quality_router, prefix="/api/v1")
app.include_router(admin_users_router, prefix="/api/v1")
app.include_router(traffic_signs_router, prefix="/api/v1")


@app.get("/health")
async def health():
    try:
        admin_quality_route = str(app.url_path_for("get_quality_overview"))
    except KeyError:
        admin_quality_route = ""
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "commit": getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
        "admin_quality_route": admin_quality_route == "/api/v1/admin/quality/overview",
    }
