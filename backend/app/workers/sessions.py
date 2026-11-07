"""Task định kỳ của phiên giảng. Chủ: Đăng (C1-07).

`reconcile_completed`: phát lại `session.completed` bị mất khi Redis / bên nghe lỗi (#94). Beat chạy 2 phút/lần.
"""

from app.db.session import SessionLocal
from app.services.session_orchestrator import reconcile_completed
from app.workers.celery_app import celery


@celery.task(name="app.workers.sessions.reconcile_completed")
def reconcile_completed_task() -> int:
    db = SessionLocal()
    try:
        return reconcile_completed(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
