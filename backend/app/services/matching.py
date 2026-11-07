"""MatchingService – Vòng ghép cặp, phản hồi gợi ý, xác nhận lại (UC15, UC22, UC23). Chủ: Long (C2-14, C2-15)."""


class MatchingService:
    def run_round(self, class_id, trigger, priority_node_id=None):
        raise NotImplementedError("C2-14")

    def accept(self, match_id, student_id):
        raise NotImplementedError("C2-14")

    def decline(self, match_id, student_id):
        raise NotImplementedError("C2-14")

    def mark_studied(self, match_id, student_id):
        raise NotImplementedError("C2-14")

    def refresh_verification(self, match_id):
        raise NotImplementedError("C2-14")
