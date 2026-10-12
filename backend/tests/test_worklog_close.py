from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.worklogs import MonthCloseIn, MonthReopenIn
from app.services.worklog_calc import lock_end


def test_lock_end():
    assert lock_end([]) is None
    assert lock_end([date(2026, 8, 1), date(2026, 9, 1)]) == date(2026, 9, 30)   # 가장 늦은 마감 달 말일
    assert lock_end([date(2026, 2, 1)]) == date(2026, 2, 28)


def test_close_schemas():
    assert MonthCloseIn(month=date(2026, 10, 1)).memo is None
    assert MonthReopenIn(month=date(2026, 10, 1), reason="퇴근 오기 수정").reason == "퇴근 오기 수정"
    with pytest.raises(ValidationError):
        MonthReopenIn(month=date(2026, 10, 1), reason="")        # 사유 필수
