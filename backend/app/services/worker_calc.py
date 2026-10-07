"""S2-P0 인력 급여 계산 순수 함수 (DB 없음 → 단위 테스트 대상).

[확정 규칙 2026-10-06]
- 정규직 = 월급 + 인센티브. 그 외(근로소득·사업자·프리랜서) = 시급제
- 출근 = 인정 출근(지문이 지정 시각보다 빠르면 지정 시각), 퇴근 = 지문 퇴근
- ① 기본급 = 시급 × 월 전체 유급 분 ÷ 60. 초과 시간도 포함, 반올림은 월 합계 1회
     → 근무표 엑셀 '월급여'와 같아야 한다 (2026-09 검증)
- ② 초과수당 = 날짜별 계약 시간대(지정 출근~지정 퇴근) 밖 근무 분 → 단위(분)마다 지정 금액, 단위 미만 버림
     → [2026-10-07] 근무표 엑셀에는 넣지 않음. 시스템 화면에 '예상'으로만 표시 (기준 있을 때)
- ③ 인센티브·주말수당·기타 (월 입력)
- ④ 근무표 지급 = ① + ③ (+ 사업자 부가세 10%)  ← 엑셀 총지급액과 같아야 한다
     예상 총액   = ① + ② + ③ (+ 사업자 부가세 10%)  ← 시스템 표시 전용
"""
from __future__ import annotations

from datetime import time


def _min(t: time | None) -> int | None:
    return None if t is None else t.hour * 60 + t.minute


def recognized_in(punch: time | None, sched_start: time | None) -> time | None:
    """지문 출근이 지정 시각보다 빠르면 지정 시각, 늦으면 실제 시각 (직접 입력용).
    엑셀 출근 칸은 이미 인정 시각이므로 그대로 쓴다."""
    if punch is None or sched_start is None:
        return punch
    return max(punch, sched_start)


def overtime_pay(ot_min: int, unit_min: int, unit_amount: int) -> int:
    """② 하루 초과수당. 단위 0 또는 금액 0 = 초과수당 없음."""
    if unit_min <= 0 or unit_amount <= 0 or ot_min <= 0:
        return 0
    return (int(ot_min) // int(unit_min)) * int(unit_amount)


def day_calc(clock_in: time | None, clock_out: time | None, *, break_min: int, break_paid: bool,
             work_start: time | None, work_end: time | None,
             ot_unit_min: int = 0, ot_unit_amount: int = 0) -> dict:
    """하루 계산.
    paid   = 유급 분 (기본급 대상, 초과 포함)
    ot     = 계약 시간대 밖 분 (참고 표시 + 초과수당 기준)
    ot_pay = 그날 초과수당"""
    i, o = _min(clock_in), _min(clock_out)
    if i is None or o is None or o <= i:
        return {"span": 0, "paid": 0, "ot": 0, "ot_pay": 0}
    span = o - i
    paid = span if break_paid else max(0, span - int(break_min or 0))
    ws, we = _min(work_start), _min(work_end)
    ot = 0
    if ws is not None and we is not None and we > ws:
        ot = max(0, ws - i) + max(0, o - we)
    ot = min(ot, paid)
    return {"span": span, "paid": paid, "ot": ot, "ot_pay": overtime_pay(ot, ot_unit_min, ot_unit_amount)}


def month_pay(days: list[dict]) -> dict:
    """days = [{paid, ot, rate, ot_pay}, ...] (월 중 시급 변경도 날짜별 rate로 합산).
    base     = ① 기본급 (전체 유급 분, 엑셀 월급여와 대조)
    ot_min   = 그중 계약 시간 밖 분 (참고 표시, 금액 분리 없음)
    ot_allow = ② 초과수당 합계"""
    return {
        "paid_min": sum(int(d["paid"]) for d in days),
        "ot_min": sum(int(d["ot"]) for d in days),
        "base": (sum(int(d["paid"]) * int(d["rate"]) for d in days) + 30) // 60,
        "ot_allow": sum(int(d["ot_pay"]) for d in days),
    }


def pay_total(base: int, ot_allow: int, extras: int, vat_applied: bool) -> dict:
    """④ 공급가, ⑤ 부가세, ⑥ 지급 합계."""
    supply = int(base) + int(ot_allow) + int(extras)
    vat = (supply + 5) // 10 if vat_applied else 0
    return {"supply": supply, "vat": vat, "total": supply + vat}


def pay_summary(base: int, ot_allow: int, extras: int, vat_applied: bool, has_ot_rule: bool) -> dict:
    """근무표(제출) 금액과 시스템 예상 금액을 나눠 계산.
    sheet    = 근무표 엑셀에 쓰는 값: 기본급 + 월 수당 (+부가세). 초과수당 없음
    expected = 화면 표시용: sheet + 예상 초과수당 (+부가세). 그 달 초과 기준이 없으면 None
    has_ot_rule = 그 달 근무일 계약 중 하나라도 초과 단위·금액이 있으면 True (호출하는 쪽에서 판단)"""
    sheet = pay_total(base, 0, extras, vat_applied)
    if not has_ot_rule:
        return {"sheet": sheet, "ot_allow": None, "expected": None}
    return {"sheet": sheet, "ot_allow": int(ot_allow),
            "expected": pay_total(base, ot_allow, extras, vat_applied)}


def resolve_accounts(fixed: dict[int, int | None], overrides: dict[int, int | None]) -> dict[int, int]:
    """그날 계정별 사용자. fixed={worker: 고정 manager}, overrides={manager: worker | None(미사용)}.
    예외로 다른 계정에 간 사람의 원래 계정은 그날 비운다. 반환 {manager: worker}."""
    acc = {mid: wid for wid, mid in fixed.items() if mid is not None}
    moved = {w for w in overrides.values() if w is not None}
    acc = {m: w for m, w in acc.items() if w not in moved}
    for mid, wid in overrides.items():
        if wid is None:
            acc.pop(mid, None)
        else:
            acc[mid] = wid
    return acc


INCOME_TYPES = ("regular", "employee", "business", "freelancer")
INCOME_PAY = {"regular": "monthly", "employee": "hourly", "business": "hourly", "freelancer": "hourly"}


def check_rate(income_type: str, r: dict) -> dict:
    """계약 조건 검증 → 저장할 값. 규칙 위반은 ValueError (메시지 그대로 화면 표시).
    정규직 = 월급(지정 시각·초과수당 없음), 그 외 = 시급 + 지정 출퇴근 필수"""
    if income_type not in INCOME_PAY:
        raise ValueError("소득 구분이 올바르지 않습니다")
    pt = r.get("pay_type")
    out = {**r, "amount": int(r.get("amount") or 0), "vat_applied": bool(r.get("vat_applied")),
           "break_min": int(r.get("break_min") or 0), "break_paid": bool(r.get("break_paid")),
           "ot_unit_min": int(r.get("ot_unit_min") or 0), "ot_unit_amount": int(r.get("ot_unit_amount") or 0)}
    if pt == "none":
        return {**out, "amount": 0, "vat_applied": False, "work_start": None, "work_end": None,
                "break_min": 0, "ot_unit_min": 0, "ot_unit_amount": 0}
    want = INCOME_PAY[income_type]
    if pt != want:
        raise ValueError("정규직은 월급제만 입력할 수 있습니다" if want == "monthly"
                         else "정규직 외 인력은 시급제만 입력할 수 있습니다")
    if out["amount"] <= 0:
        raise ValueError("금액을 입력하세요")
    if pt == "monthly":
        return {**out, "work_start": None, "work_end": None, "break_min": 0,
                "ot_unit_min": 0, "ot_unit_amount": 0}
    ws, we = r.get("work_start"), r.get("work_end")
    if ws is None or we is None:
        raise ValueError("시급제는 지정 출근·퇴근 시각이 필요합니다 (초과 판정 기준)")
    span = _min(we) - _min(ws)
    if span <= 0:
        raise ValueError("지정 퇴근은 지정 출근보다 늦어야 합니다 (자정 넘김 미지원)")
    if out["break_min"] >= span:
        raise ValueError("휴게시간이 근무시간보다 깁니다")
    if (out["ot_unit_min"] > 0) != (out["ot_unit_amount"] > 0):
        raise ValueError("초과수당 단위(분)와 금액은 둘 다 입력하거나 둘 다 비워 두세요")
    return out

