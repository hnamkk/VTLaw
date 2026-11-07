"""Application settings loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env (config.py nằm tại app/backend/src/core/ -> lên 4 cấp).
_REPO_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Ưu tiên .env ở thư mục hiện tại, fallback về .env ở repo root để
        # alembic/pytest chạy từ app/backend vẫn nạp đúng biến môi trường.
        env_file=(".env", str(_REPO_ROOT_ENV)),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM ----
    OPENAI_API_KEY: str = ""
    MODEL_NAME: str = "gpt-4o-mini"

    # ---- Embedding ----
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    QUERY_EMBEDDING_MAX_CHARS: int = 6000

    # ---- Database ----
    # BẮT BUỘC set qua biến môi trường (.env). Default dưới đây chỉ là placeholder
    # KHÔNG chứa credential thật và sẽ không kết nối được — tránh rủi ro dùng nhầm
    # mật khẩu mặc định ở môi trường production.
    DATABASE_URL: str = "postgresql+asyncpg://CHANGE_ME:CHANGE_ME@localhost:5433/legalai_db"

    # ---- App ----
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    MAX_UPLOAD_FILE_SIZE_MB: int = 128
    MAX_CONCURRENT_UPLOADS: int = 2
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    PUBLIC_CHAT_RATE_LIMIT_ENABLED: bool = True
    PUBLIC_CHAT_RATE_LIMIT_BURST_REQUESTS: int = 6
    PUBLIC_CHAT_RATE_LIMIT_BURST_WINDOW_SECONDS: int = 60
    PUBLIC_CHAT_RATE_LIMIT_SUSTAINED_REQUESTS: int = 30
    PUBLIC_CHAT_RATE_LIMIT_SUSTAINED_WINDOW_SECONDS: int = 600
    DOCUMENT_LIFECYCLE_SYNC_ENABLED: bool = True
    DOCUMENT_LIFECYCLE_SYNC_INTERVAL_SECONDS: int = 3600

    # ---- LangSmith ----
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "ai20k-agent"
    LANGCHAIN_TRACING_V2: bool = False

    # ---- Langfuse observability ----
    LANGFUSE_TRACING_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_SAMPLE_RATE: float = 1.0
    QUALITY_MIN_PRODUCTION_SAMPLE: int = 20

    # ---- Logging ----
    LOG_LEVEL: str = "INFO"

    # ---- Object Storage ----
    OBJECT_STORAGE_ENABLED: bool = False
    OBJECT_STORAGE_PROVIDER: str = "s3"
    S3_ENDPOINT_URL: str = ""
    S3_REGION: str = "auto"
    S3_BUCKET: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_PUBLIC_BASE_URL: str = ""
    S3_PRESIGNED_URL_EXPIRE_SECONDS: int = 300
    KB_REQUIRE_OBJECT_STORAGE: bool = False
    KB_LOCAL_STORAGE_PATH: str = "app/backend/storage/legal_kb"

    # ---- RAG tuning ----
    # Retrieval
    RETRIEVAL_VECTOR_TOP_K: int = 40
    RETRIEVAL_FTS_TOP_K: int = 40
    RETRIEVAL_MERGE_TOP_K: int = 60
    RETRIEVAL_EXACT_TOP_K: int = 10
    RETRIEVAL_MAX_PER_DOCUMENT: int = 8
    LOCAL_RANK_TOP_K: int = 12
    CONTEXT_PACK_SIZE: int = 8
    # Maximum context size in tokens for the prompt (spec 11 §7).
    # Budget enforced at ~2.5 chars/token (conservative for Vietnamese legal text).
    CONTEXT_TOKEN_BUDGET: int = 4000
    # Minimum local ranking score to trust as evidence (spec 11 §8).
    LOCAL_RANK_MIN_SCORE: float = 0.24
    LOCAL_RANK_VERSION: str = "legal-rank-v2"
    # Hybrid scoring weights
    HYBRID_VECTOR_WEIGHT: float = 0.65
    HYBRID_FTS_WEIGHT: float = 0.35
    RETRIEVAL_FTS_MAX_TERMS: int = 48
    # Scope classifier thresholds
    SCOPE_IN_THRESHOLD: float = 0.72
    SCOPE_UNCERTAIN_THRESHOLD: float = 0.58
    # Chunking thresholds (chars)
    CHUNK_MIN_LEN: int = 80
    CHUNK_MAX_LEN: int = 1500
    EMBEDDING_CONTENT_MAX_LEN: int = 2500

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def kb_local_storage_path(self) -> str:
        return self.KB_LOCAL_STORAGE_PATH or "app/backend/storage/legal_kb"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.APP_ENV.lower() == "production" and self.JWT_SECRET_KEY in {
            "",
            "change-me-in-production",
            "your-super-secret-jwt-key-change-in-production",
            "replace-with-a-long-random-secret",
        }:
            raise ValueError("JWT_SECRET_KEY must be set to a strong secret in production.")
        if self.OBJECT_STORAGE_ENABLED:
            missing = [
                name
                for name, value in {
                    "S3_BUCKET": self.S3_BUCKET,
                    "S3_ACCESS_KEY_ID": self.S3_ACCESS_KEY_ID,
                    "S3_SECRET_ACCESS_KEY": self.S3_SECRET_ACCESS_KEY,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    "Object storage is enabled but missing env vars: " + ", ".join(missing)
                )
        if self.KB_REQUIRE_OBJECT_STORAGE and not self.OBJECT_STORAGE_ENABLED:
            raise ValueError(
                "KB_REQUIRE_OBJECT_STORAGE=true requires OBJECT_STORAGE_ENABLED=true."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
