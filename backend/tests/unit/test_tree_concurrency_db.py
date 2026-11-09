"""C2-09: real Postgres regressions for concurrent edits and publication."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.errors import AppError
from app.models import tree as orm
from app.models.enums import Role, TreeStatus
from app.models.schemas.session import DEFAULT_CRITERION_WEIGHTS
from app.models.schemas.tree import Edge, KeyPointSchema, Node, NodePatch, Rubric, TreeVersion
from app.models.session import TeachingSession
from app.models.users import ClassSection, Course, User
from app.services import skill_tree as module
from app.services.skill_tree import SkillTreeService
from tests.unit.test_tree_edit_db import World

DB_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="requires migrated Postgres")


@pytest.fixture
def committed_world():
    engine = create_engine(DB_URL)
    with Session(engine) as db:
        world = World(db)
        course_id = db.get(ClassSection, world.class_id).course_id
        db.commit()
    user = CurrentUser(id=world.gv, role=Role.LECTURER)
    try:
        yield engine, world, user
    finally:
        with Session(engine) as db:
            db.execute(delete(TeachingSession).where(TeachingSession.class_id == world.class_id))
            db.execute(delete(ClassSection).where(ClassSection.id == world.class_id))
            db.execute(delete(Course).where(Course.id == course_id))
            db.execute(delete(User).where(User.id.in_(world.roles)))
            db.commit()
        engine.dispose()


def draft(engine, world, user):
    valid = Rubric(key_points=[KeyPointSchema(id="KP1", content="ý chính")])  # rubric rỗng không duyệt được (C2-23)
    body = TreeVersion(nodes=[Node(key=k, title=k, rubric=valid) for k in ("a", "b")], edges=[])
    with Session(engine) as db:
        service = SkillTreeService(db)
        tree = service.create_version(world.class_id, user, body)
        for node in tree.nodes:
            service.put_rubric(node.id, node.rubric.model_copy(update={"approved": True}), user)
        return tree


def result(operation):
    try:
        operation()
        return "ok"
    except AppError as error:
        return error.code


def test_opposite_concurrent_edges_cannot_form_cycle(committed_world, monkeypatch):
    engine, world, user = committed_world
    tree = draft(engine, world, user)
    first_read, second_read, release = Event(), Event(), Event()
    original = module.would_create_cycle

    def paused_validation(*args):
        path = original(*args)
        if current_thread().name.endswith("_0"):
            first_read.set()
            assert release.wait(5)
        else:
            second_read.set()
        return path

    monkeypatch.setattr(module, "would_create_cycle", paused_validation)

    def add(source, target):
        with Session(engine) as db:
            return result(lambda: SkillTreeService(db).add_edge(tree.id, Edge(from_key=source, to_key=target), user))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(add, "a", "b")
        assert first_read.wait(5)
        second = pool.submit(add, "b", "a")
        second_read.wait(0.5)
        release.set()
        assert sorted([first.result(timeout=5), second.result(timeout=5)]) == ["CYCLE_DETECTED", "ok"]


def paused_publisher(db, entered, release):
    class Publisher(SkillTreeService):
        paused = False

        def _to_schema(self, *args):
            schema = super()._to_schema(*args)
            if not self.paused:
                self.paused = True
                entered.set()
                assert release.wait(5)
            return schema

    return Publisher(db)


def test_concurrent_publish_leaves_only_one_published_version(committed_world):
    engine, world, user = committed_world
    first_tree, second_tree = draft(engine, world, user), draft(engine, world, user)
    entered, release, second_done = Event(), Event(), Event()

    def first_publish():
        with Session(engine) as db:
            return paused_publisher(db, entered, release).publish(first_tree.id, user)

    def second_publish():
        try:
            with Session(engine) as db:
                return SkillTreeService(db).publish(second_tree.id, user)
        finally:
            second_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_publish)
        assert entered.wait(5)
        second = pool.submit(second_publish)
        second_done.wait(0.5)
        release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    with Session(engine) as db:
        tree = db.scalar(select(orm.SkillTree).where(orm.SkillTree.class_id == world.class_id))
        published = list(
            db.scalars(
                select(orm.TreeVersion).where(
                    orm.TreeVersion.tree_id == tree.id, orm.TreeVersion.status == TreeStatus.PUBLISHED
                )
            )
        )
        assert [v.id for v in published] == [tree.published_version_id]


def test_edit_waiting_for_publish_cannot_mutate_published_version(committed_world):
    engine, world, user = committed_world
    tree = draft(engine, world, user)
    entered, release, edited = Event(), Event(), Event()

    def publish():
        with Session(engine) as db:
            return paused_publisher(db, entered, release).publish(tree.id, user)

    def edit():
        try:
            with Session(engine) as db:
                return result(
                    lambda: SkillTreeService(db).update_node(tree.nodes[0].id, NodePatch(title="changed"), user)
                )
        finally:
            edited.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(publish)
        assert entered.wait(5)
        second = pool.submit(edit)
        edited.wait(0.5)
        release.set()
        first.result(timeout=5)
        assert second.result(timeout=5) == "VERSION_NOT_EDITABLE"
    with Session(engine) as db:
        assert db.get(orm.ConceptNode, tree.nodes[0].id).title == "a"


def test_edit_rubric_preserves_criterion_ids_and_weights(committed_world):
    engine, world, user = committed_world
    tree = draft(engine, world, user)
    node = tree.nodes[0]
    with Session(engine) as db:
        rubric = db.scalar(select(orm.Rubric).where(orm.Rubric.node_id == node.id))
        existing = list(db.scalars(select(orm.RubricCriterion).where(orm.RubricCriterion.rubric_id == rubric.id)))
        if not existing:
            for code, weight in DEFAULT_CRITERION_WEIGHTS.items():
                db.add(
                    orm.RubricCriterion(
                        rubric_id=rubric.id, code=code.value, name=code.value, weight=weight, max_score=100
                    )
                )
            db.commit()
        criteria = list(db.scalars(select(orm.RubricCriterion).where(orm.RubricCriterion.rubric_id == rubric.id)))
        before = {c.id: (c.code, c.weight, c.max_score) for c in criteria}
        rubric_id = rubric.id
        SkillTreeService(db).put_rubric(node.id, node.rubric.model_copy(update={"pass_threshold": 75}), user)
        after = list(db.scalars(select(orm.RubricCriterion).where(orm.RubricCriterion.rubric_id == rubric_id)))
        assert {c.id: (c.code, c.weight, c.max_score) for c in after} == before
