"""Điểm vào FastAPI. Router được nạp tự động: mỗi module trong app/api/ có biến `router`
sẽ được gắn vào tiền tố /api/v1 – thêm endpoint mới không cần sửa file này (thẻ C2-01).
"""

import importlib
import logging
import pkgutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import api
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging

log = logging.getLogger(__name__)


def include_routers(app: FastAPI, prefix: str) -> list[str]:
    loaded = []
    for mod in pkgutil.iter_modules(api.__path__):
        if mod.name.startswith("_") or mod.name == "deps":
            continue
        module = importlib.import_module(f"{api.__name__}.{mod.name}")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router, prefix=prefix)
            loaded.append(mod.name)
    return loaded


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="Whybi AI API",
        version="0.1.0",
        description="Nền tảng “Sinh viên làm thầy, AI làm học trò” – đội WhyBloom (Hackathon SGU 2026–2027)",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env, "llm_mode": settings.llm_mode}

    loaded = include_routers(app, settings.api_prefix)
    log.info("routers loaded: %s", ", ".join(loaded))
    return app


app = create_app()
