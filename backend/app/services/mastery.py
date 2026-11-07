"""MasteryService – Ma trận thành thạo + MasteryStateMachine (Bảng 4.8, BR-02, BR-11, BR-14). Nhận
session.completed, phát mastery.changed. Chủ: Long (C2-10).
"""


class MasteryService:
    def can_start(self, student_id, node_id):
        raise NotImplementedError("C2-10")

    def apply_result(self, result):
        raise NotImplementedError("C2-10")

    def init_or_migrate(self, class_id, version_id):
        raise NotImplementedError("C2-10")

    def my_map(self, class_id, student_id):
        raise NotImplementedError("C2-10")
