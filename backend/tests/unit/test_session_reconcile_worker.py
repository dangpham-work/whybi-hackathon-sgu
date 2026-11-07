"""#94 – task Celery đối soát session.completed bị mất: có trong lịch beat, mở / đóng phiên CSDL đúng cách."""

from unittest.mock import Mock

import pytest

TASK = "app.workers.sessions.reconcile_completed"


def test_reconcile_task_is_registered_and_scheduled_every_two_minutes():
    from app.workers.celery_app import celery

    assert "app.workers.sessions" in celery.conf.include
    entry = next(e for e in celery.conf.beat_schedule.values() if e["task"] == TASK)
    assert entry["schedule"] == 120.0
    celery.loader.import_default_modules()
    assert TASK in celery.tasks


def test_reconcile_task_runs_orchestrator_and_closes_db(monkeypatch):
    import app.workers.sessions as mod

    db = Mock()
    run = Mock(return_value=3)
    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(mod, "reconcile_completed", run)
    assert mod.reconcile_completed_task.run() == 3
    run.assert_called_once_with(db)
    db.close.assert_called_once()


def test_reconcile_task_closes_db_on_error(monkeypatch):
    import app.workers.sessions as mod

    db = Mock()
    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(mod, "reconcile_completed", Mock(side_effect=RuntimeError("db down")))
    with pytest.raises(RuntimeError):
        mod.reconcile_completed_task.run()
    db.rollback.assert_called_once()
    db.close.assert_called_once()
