"""NotificationService – Thông báo trong ứng dụng (kênh user:{id}) và email (FR-AD-08). Chủ: Long (C2-19)."""


class NotificationService:
    def notify(self, user_id, type, title, link=None):
        raise NotImplementedError("C2-19")
