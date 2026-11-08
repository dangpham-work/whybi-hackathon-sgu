"""Model chỉ nhận temperature mặc định (dòng suy luận): provider tự thử lại không gửi tham số đó và nhớ lại."""

import json

import httpx
import pytest

from app.ai.providers import OpenAICompatProvider
from app.ai.providers.base import PermanentProviderError

OK = {"choices": [{"message": {"content": "{}"}}], "usage": {}}
REJECT = {
    "error": {"message": "Unsupported value: 'temperature' does not support 0 with this model.", "param": "temperature"}
}


def _provider(handler) -> tuple[OpenAICompatProvider, list[dict]]:
    sent: list[dict] = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content))
        return handler(req, sent)

    client = httpx.Client(transport=httpx.MockTransport(wrapped))
    return OpenAICompatProvider("http://llm.local/v1", "k", "gpt-6-luna", http_client=client), sent


def test_bi_tu_choi_temperature_thi_thu_lai_khong_gui_va_nho_lai():
    p, sent = _provider(
        lambda req, sent: (
            httpx.Response(400, json=REJECT) if "temperature" in sent[-1] else httpx.Response(200, json=OK)
        )
    )
    p.complete([{"role": "user", "content": "x"}], {}, model="gpt-6-luna", temperature=0)
    assert ["temperature" in b for b in sent] == [True, False]
    p.complete([{"role": "user", "content": "y"}], {}, model="gpt-6-luna", temperature=0)
    assert len(sent) == 3 and "temperature" not in sent[2]  # lần sau không gửi ngay


def test_loi_400_khac_van_nem_ra():
    p, sent = _provider(lambda req, sent: httpx.Response(400, json={"error": {"message": "model not found"}}))
    with pytest.raises(PermanentProviderError):
        p.complete([{"role": "user", "content": "x"}], {}, model="gpt-6-luna", temperature=0)
    assert len(sent) == 1
