from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.incentive import HoldIn, QtyAdjIn, ReasonIn


@pytest.mark.parametrize("v", ["", "   "])
def test_reason_required(v):
    with pytest.raises(ValidationError):
        ReasonIn(reason=v)
    with pytest.raises(ValidationError):
        HoldIn(manager_id=1, reason=v)
    with pytest.raises(ValidationError):
        QtyAdjIn(work_date=date(2026, 10, 13), manager_id=1, product_id=23, qty=-3, reason=v)


def test_reason_trimmed():
    assert ReasonIn(reason="  배송 지연  ").reason == "배송 지연"
