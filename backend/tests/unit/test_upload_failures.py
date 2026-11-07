"""C2-08: lỗi hạ tầng phải trả nhanh, không lọt lỗi transport thành HTTP 500."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from celery import Celery
from kombu import Connection
from kombu.exceptions import OperationalError
from redis import Connection as RedisConnection
from redis.exceptions import ConnectionError as RedisConnectionError
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

from app.services.storage import MinioStorage, StorageUnavailable


@pytest.mark.parametrize("operation", ["put", "get", "remove"])
@pytest.mark.parametrize("error", [MaxRetryError(None, "/"), ReadTimeoutError(None, "/", "timeout")])
def test_minio_transport_failure_is_storage_unavailable(operation, error):
    storage = MinioStorage("http://localhost:9000", "test", "test", "test")
    storage.client = Mock()
    storage.client.bucket_exists.side_effect = error
    storage.client.get_object.side_effect = error
    storage.client.remove_object.side_effect = error
    with pytest.raises(StorageUnavailable) as exc:
        if operation == "put":
            storage.put("a.pdf", b"%PDF-", "application/pdf")
        else:
            getattr(storage, operation)("s3://test/a.pdf")
    assert exc.value.__cause__ is error


def test_enqueue_does_not_subscribe_to_redis_result_backend(monkeypatch):
    from app.services.syllabus import CeleryJobQueue
    from app.workers import celery_app

    celery = Celery("upload-test", broker="memory://", backend="redis://localhost:1/0")
    subscribe = Mock(side_effect=ConnectionError("Redis result backend is down"))
    monkeypatch.setattr(celery.backend, "on_task_call", subscribe)
    monkeypatch.setattr(celery_app, "celery", celery)
    CeleryJobQueue().enqueue_syllabus(uuid4(), str(uuid4()))
    subscribe.assert_not_called()


def test_enqueue_broker_failure_does_not_retry_or_sleep(monkeypatch):
    from app.services.syllabus import CeleryJobQueue
    from app.workers import celery_app

    celery = Celery("upload-test", broker="redis://localhost:1/0", backend="cache+memory://")
    connect = Mock(side_effect=OSError("Redis broker is down"))
    sleep = Mock()
    monkeypatch.setattr(Connection, "_establish_connection", connect)
    monkeypatch.setattr("kombu.utils.functional.sleep", sleep)
    monkeypatch.setattr(celery_app, "celery", celery)
    with pytest.raises(OperationalError):
        CeleryJobQueue().enqueue_syllabus(uuid4(), str(uuid4()))
    assert connect.call_count == 1
    sleep.assert_not_called()


def test_enqueue_redis_socket_timeouts_are_bounded(monkeypatch):
    from app.services.syllabus import CeleryJobQueue
    from app.workers import celery_app

    celery = Celery("upload-timeout-test", broker="redis://localhost:1/0", backend="cache+memory://")
    timeouts = []

    def fail_connect(connection):
        timeouts.append((connection.socket_connect_timeout, connection.socket_timeout))
        raise RedisConnectionError("Redis broker is down")

    monkeypatch.setattr(RedisConnection, "_connect", fail_connect)
    monkeypatch.setattr("kombu.utils.functional.sleep", Mock())
    monkeypatch.setattr(celery_app, "celery", celery)
    with pytest.raises(OperationalError):
        CeleryJobQueue().enqueue_syllabus(uuid4(), str(uuid4()))
    assert timeouts == [(2, 2)]


def test_enqueue_routes_document_task_with_job_id(monkeypatch):
    from app.services.syllabus import TASK_PROCESS_SYLLABUS, CeleryJobQueue
    from app.workers import celery_app

    celery = Celery("upload-success-test", broker="memory://", backend="cache+memory://")
    queue_name = f"documents-test-{uuid4()}"
    celery.conf.task_routes = {"app.workers.documents.*": {"queue": queue_name}}
    monkeypatch.setattr(celery_app, "celery", celery)
    document_id, job_id = uuid4(), str(uuid4())
    CeleryJobQueue().enqueue_syllabus(document_id, job_id)
    with celery.connection_for_read() as connection, connection.SimpleQueue(queue_name) as queue:
        message = queue.get(block=False)
        try:
            assert message.headers["task"] == TASK_PROCESS_SYLLABUS
            assert message.headers["id"] == job_id
            assert message.payload[0] == [str(document_id), job_id]
        finally:
            message.ack()
