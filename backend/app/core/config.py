"""Cấu hình ứng dụng – đọc từ biến môi trường / .env (xem .env.example ở gốc repo)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: Literal["dev", "demo", "prod", "test"] = "dev"
    app_name: str = "Whybi AI"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost"
    log_level: str = "INFO"
    log_json: bool = True

    # Chế độ AI (mục 3.3 kế hoạch phân công)
    llm_mode: Literal["fake", "real"] = "fake"
    demo_mode: bool = False

    # LLM – FR-AD-05, NFR-14 (giá trị khởi đầu; QTV ghi đè qua PUT /admin/ai-config)
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"
    llm_fallback_provider: str = "openai_compat"
    llm_fallback_model: str = ""
    llm_guard_model: str = "gemini-2.5-flash-lite"
    gemini_api_key: str = ""
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    llm_session_token_budget: int = 20_000
    paste_ratio_threshold: float = 0.6
    paste_min_chars: int = 120
    typing_cps_max: float = 20.0
    llm_timeout_s: float = 30
    llm_max_retries: int = 2
    llm_transient_retries: int = 1
    llm_cache_size: int = 256
    llm_embedding_model: str = "gemini-embedding-001"
    openai_compat_json_mode: Literal["json_schema", "json_object"] = "json_schema"
    embedding_dim: int = 768

    # Giọng nói – mục 6.4
    stt_provider: str = "cloud"
    stt_whisper_url: str = "http://stt:8000"  # cổng trong container; host dùng STT_PORT
    stt_min_confidence: float = 0.80
    tts_provider: str = "cloud"
    audio_retention_days: int = 30

    # Xác thực – NFR-07
    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_access_minutes: int = 30
    jwt_refresh_days: int = 7
    # TẠM tới C2-07: nhận token "dev-lecturer|dev-student|dev-admin". Mặc định TẮT; chỉ có tác dụng khi
    # APP_ENV=dev|test và DEMO_MODE tắt (xem app/api/deps.py).
    allow_dev_tokens: bool = False

    # Hạ tầng (mặc định trỏ tới tên dịch vụ trong docker-compose.yml)
    database_url: str = "postgresql+psycopg://whybi:whybi@postgres:5432/whybi"
    redis_url: str = "redis://redis:6379/0"
    # Bus sự kiện (C2-05). memory: một tiến trình, không cần Redis; APP_ENV=test luôn dùng memory.
    event_bus: Literal["redis", "memory"] = "redis"
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "whybi"
    s3_secret_key: str = "whybi-minio-secret"
    s3_bucket: str = "whybi"
    max_syllabus_mb: int = 20
    # Cổng cỡ giáo trình (syllabus_toc): ước số nút cây ≥ toc_warn_nodes ⇒ AI viết cảnh báo và (khi toc_gate_enabled)
    # dừng chờ GV chọn chương trước khi tốn token dựng cây; ≥ toc_max_nodes ⇒ mức "quá lớn".
    toc_gate_enabled: bool = True
    toc_warn_nodes: int = 60
    toc_max_nodes: int = 150

    # Dữ liệu mẫu (seed/ ở gốc repo; trong Docker mount vào /seed). Rỗng ⇒ tự dò <repo>/seed.
    seed_dir: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "whybi@example.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
