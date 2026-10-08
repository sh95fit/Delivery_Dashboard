import pytest
from pydantic import ValidationError

from app.schemas.worklogs import WorkPersonIn


def test_person_in_parses():
    b = WorkPersonIn(items=[{"work_date": "2026-10-07", "clock_out": "12:40"}], delete_ids=[3])
    assert b.items[0].work_date.day == 7 and b.items[0].punch_in is None and b.delete_ids == [3]


def test_person_in_requires_something():
    with pytest.raises(ValidationError):
        WorkPersonIn(items=[], delete_ids=[])


def test_person_in_limits():
    with pytest.raises(ValidationError):
        WorkPersonIn(items=[{"work_date": "2026-10-07", "clock_out": "12:40", "break_min": 601}])
