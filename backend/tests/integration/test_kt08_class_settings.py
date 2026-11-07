"""KT-08: cấu hình lớp trả đúng số câu phản biện GV đặt (cột challenge_count đã có trên main)."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.services.classes import ClassService


def test_cau_hinh_lop_tra_so_cau_phan_bien_da_dat():
    section = SimpleNamespace(
        pass_threshold=80, color_thresholds={"green": 0.8, "yellow": 0.4}, min_sample=5, challenge_count=5
    )
    database = Mock()
    database.get.return_value = section

    settings = ClassService(database).get_settings(uuid4())

    assert settings.challenge_count == 5
    assert settings.pass_threshold == 80
    assert settings.green_threshold == 0.8
