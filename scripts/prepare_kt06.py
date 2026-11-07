"""Seed cho KT-06; chạy trong container API fake, trả metadata JSON cho Playwright.

Tái sử dụng seed_db, không sửa điểm hoặc phát hành cây demo. Cây của từng ca test
được tạo/duyệt/phát hành qua HTTP trong sv-flow.spec.ts.
"""

import json
import sys

from seed_db import check_seed, load_seed, write_db


def prepare() -> dict:
    from app.core.config import get_settings
    from app.models.users import Course
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    settings = get_settings()
    if settings.app_env not in {"dev", "test"} or settings.llm_mode != "fake":
        raise ValueError("KT-06 chỉ seed trong APP_ENV=dev|test và LLM_MODE=fake")
    if make_url(settings.database_url).host != "postgres":
        raise ValueError("KT-06 chỉ tự seed PostgreSQL nội bộ của Docker Compose")
    bundle = load_seed()
    errors = check_seed(bundle)
    if errors:
        raise ValueError("Seed không hợp lệ: " + "; ".join(errors))

    engine = create_engine(settings.database_url)
    try:
        # Hai project Playwright có thể khởi động đồng thời trên DB còn trống.
        # Giữ khóa và transaction ngoài xuyên qua commit nội bộ của write_db.
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(62006)"))
            with Session(bind=connection, join_transaction_mode="rollback_only") as db:
                created = write_db(db, bundle)
                course_id = db.scalar(
                    select(Course.id).where(Course.code == bundle.klass.course.code)
                )
                if course_id is None:
                    raise ValueError("Không tìm thấy môn học sau khi nạp seed")
                result = {"courseId": str(course_id), "created": created}
        return result
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(prepare()))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
