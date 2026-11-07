"""SessionOrchestrator – Facade điều phối Tutee/Judge/Guard (mục 4.4.3, 4.5.2). Cuối phiên phát
session.completed. Chủ: Đăng (C1-07).
"""


class SessionOrchestrator:
    def start_session(self, student_id, node_id, body):
        raise NotImplementedError("C1-07")

    def handle_turn(self, session_id, turn):
        raise NotImplementedError("C1-07")

    def handle_timeout(self, session_id):
        raise NotImplementedError("C1-15")

    def finish(self, session_id):
        raise NotImplementedError("C1-07")
