import pytest
from pydantic import ValidationError

from app.schemas.worklogs import WorkOffBulkIn


def test_bulk_off_schema():
    assert WorkOffBulkIn(worker_ids=[1, 2], reason="holiday").reason == "holiday"
    assert WorkOffBulkIn(worker_ids=[1]).reason is None          # 해제
    with pytest.raises(ValidationError):
        WorkOffBulkIn(worker_ids=[], reason="holiday")            # 대상 없음
    with pytest.raises(ValidationError):
        WorkOffBulkIn(worker_ids=[1], reason="vacation")          # 없는 사유
