"""SpeechService – STT/TTS qua adapter, glossary thuật ngữ theo nút, ngưỡng tin cậy 0,80 (mục 6.4). Chủ: Đăng
(C1-12, C1-14).
"""


class SpeechService:
    def transcribe(self, audio, node_id):
        raise NotImplementedError("C1-12")

    def synthesize(self, text):
        raise NotImplementedError("C1-14")
