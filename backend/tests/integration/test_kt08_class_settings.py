"""KT-08: settings must work before the per-class challenge-count migration is ported."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.classes import ClassService


@pytest.mark.parametrize("configured", [False, True])
def test_challenge_count_supports_current_and_extended_class_models(configured):
    section = SimpleNamespace(pass_threshold=80, color_thresholds={"green": 0.8, "yellow": 0.4}, min_sample=5)
    if configured:
        section.challenge_count = 5
    database = Mock()
    database.get.return_value = section

    settings = ClassService(database).get_settings(uuid4())

    assert settings.challenge_count == (5 if configured else 3)
    assert settings.pass_threshold == 80
    assert settings.green_threshold == 0.8