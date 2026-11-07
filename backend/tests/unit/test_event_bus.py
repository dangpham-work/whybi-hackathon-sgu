"""C2-05 – Xong khi: phát sự kiện thì handler nhận đúng payload."""

import json
import threading
from uuid import uuid4

import pytest

from app.models.enums import MasteryState, Verdict
from app.models.schemas.mastery import TOPIC_MASTERY_CHANGED, TOPIC_SESSION_COMPLETED, MasteryChanged
from app.models.schemas.session import SessionResult
from app.realtime.bus import InMemoryEventBus, RedisEventBus, UnknownTopic, decode, encode, get_bus


def _mastery_changed() -> MasteryChanged:
    return MasteryChanged(
        class_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        node_key="n5_con_tro",
        old_state=MasteryState.IN_PROGRESS,
        new_state=MasteryState.MASTERED,
        unlocked_node_ids=[uuid4()],
        session_id=uuid4(),
    )


def _session_result() -> SessionResult:
    return SessionResult(
        session_id=uuid4(),
        student_id=uuid4(),
        node_id=uuid4(),
        class_id=uuid4(),
        state=MasteryState.MASTERED,
        verdict=Verdict.PASSED,
        total_score=78,
        criteria=[],
    )


# --- Mã hóa trên dây ---------------------------------------------------------------------------


def test_wire_format_is_camel_case_json():
    ev = _mastery_changed()
    data = json.loads(encode(TOPIC_MASTERY_CHANGED, ev))
    assert data["newState"] == "MASTERED" and data["nodeKey"] == "n5_con_tro"
    assert decode(TOPIC_MASTERY_CHANGED, encode(TOPIC_MASTERY_CHANGED, ev)) == ev


def test_wrong_payload_type_for_topic_rejected():
    with pytest.raises(TypeError):
        encode(TOPIC_MASTERY_CHANGED, _session_result())


def test_unknown_topic_rejected():
    with pytest.raises(UnknownTopic):
        encode("khong.co", _mastery_changed())


# --- Bus trong bộ nhớ (test, dev không Redis) ----------------------------------------------------


def test_handler_receives_exact_payload():
    bus = InMemoryEventBus()
    got: list[MasteryChanged] = []
    bus.subscribe(TOPIC_MASTERY_CHANGED, got.append)
    ev = _mastery_changed()
    bus.publish(TOPIC_MASTERY_CHANGED, ev)
    assert got == [ev]
    assert isinstance(got[0], MasteryChanged)


def test_session_completed_delivers_session_result():
    bus = InMemoryEventBus()
    got = []
    bus.subscribe(TOPIC_SESSION_COMPLETED, got.append)
    r = _session_result()
    bus.publish(TOPIC_SESSION_COMPLETED, r)
    assert got == [r] and isinstance(got[0], SessionResult)


def test_only_subscribers_of_topic_are_called_and_all_of_them():
    bus = InMemoryEventBus()
    a, b, other = [], [], []
    bus.subscribe(TOPIC_MASTERY_CHANGED, a.append)
    bus.subscribe(TOPIC_MASTERY_CHANGED, b.append)
    bus.subscribe(TOPIC_SESSION_COMPLETED, other.append)
    bus.publish(TOPIC_MASTERY_CHANGED, _mastery_changed())
    assert len(a) == len(b) == 1 and other == []


def test_failing_handler_does_not_block_others():
    bus = InMemoryEventBus()
    got = []

    def boom(_):
        raise RuntimeError("lỗi handler")

    bus.subscribe(TOPIC_MASTERY_CHANGED, boom)
    bus.subscribe(TOPIC_MASTERY_CHANGED, got.append)
    bus.publish(TOPIC_MASTERY_CHANGED, _mastery_changed())
    assert len(got) == 1


def test_chain_session_completed_to_mastery_changed():
    """Luồng mục 5.1.3: session.completed → (mastery) → mastery.changed → heatmap / matching."""
    bus = InMemoryEventBus()
    heatmap = []

    def mastery_handler(r: SessionResult) -> None:
        bus.publish(
            TOPIC_MASTERY_CHANGED,
            MasteryChanged(
                class_id=r.class_id,
                student_id=r.student_id,
                node_id=r.node_id,
                old_state=MasteryState.IN_PROGRESS,
                new_state=r.state,
                session_id=r.session_id,
            ),
        )

    bus.subscribe(TOPIC_SESSION_COMPLETED, mastery_handler)
    bus.subscribe(TOPIC_MASTERY_CHANGED, heatmap.append)
    r = _session_result()
    bus.publish(TOPIC_SESSION_COMPLETED, r)
    assert heatmap[0].student_id == r.student_id and heatmap[0].session_id == r.session_id


# --- Bus Redis với client giả (không mở mạng) ----------------------------------------------------


class FakePubSub:
    def __init__(self, broker):
        self.broker, self.channels, self.queue = broker, set(), []
        broker.subs.append(self)

    def subscribe(self, *channels):
        self.channels.update(channels)

    def get_message(self, timeout=0.0):
        return self.queue.pop(0) if self.queue else None

    def close(self):
        self.broker.subs.remove(self)


class FakeRedis:
    def __init__(self):
        self.subs: list[FakePubSub] = []
        self.published: list[tuple[str, str]] = []

    def publish(self, channel, data):
        self.published.append((channel, data))
        for s in self.subs:
            if channel in s.channels:
                s.queue.append({"type": "message", "channel": channel, "data": data})
        return 1

    def pubsub(self, ignore_subscribe_messages=True):
        return FakePubSub(self)


def test_redis_bus_publish_and_listen():
    fake = FakeRedis()
    bus = RedisEventBus(client=fake)
    got = []
    bus.subscribe(TOPIC_MASTERY_CHANGED, got.append)
    stop = threading.Event()
    ready = threading.Event()
    t = threading.Thread(target=bus.listen, kwargs={"stop": stop, "timeout": 0.01, "ready": ready}, daemon=True)
    t.start()
    assert ready.wait(2)
    ev = _mastery_changed()
    bus.publish(TOPIC_MASTERY_CHANGED, ev)
    for _ in range(200):
        if got:
            break
        stop.wait(0.01)
    stop.set()
    t.join(2)
    assert got == [ev]
    channel, data = fake.published[0]
    assert channel == TOPIC_MASTERY_CHANGED and json.loads(data)["nodeId"] == str(ev.node_id)


def test_redis_bus_skips_malformed_message():
    bus = RedisEventBus(client=FakeRedis())
    got = []
    bus.subscribe(TOPIC_MASTERY_CHANGED, got.append)
    bus.dispatch(TOPIC_MASTERY_CHANGED, "{không phải json")
    bus.dispatch(TOPIC_MASTERY_CHANGED, encode(TOPIC_MASTERY_CHANGED, _mastery_changed()))
    assert len(got) == 1


def test_get_bus_uses_memory_in_tests():
    assert isinstance(get_bus(), InMemoryEventBus)
    assert get_bus() is get_bus()
