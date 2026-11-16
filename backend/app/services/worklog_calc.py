"""S2-P4a-1 근무 기록 검증·계산 순수 함수 (DB 없음 → 단위 테스트 대상).

- 출근: 지문 시각(punch_in) → 인정 출근(clock_in). 비우면 지정 출근. 지정보다 이르면 지정 시각
  (조기 출근 인정 early_ok = 그날만 지문 시각 그대로, 한시적 출근 시각 조정)
- 휴게: 입력 = 실제 휴게 시간 (비우면 계약 휴게). 계약이 무급이면 합계에서 빼고 유급이면 빼지 않음 (근무표 '휴게' 칸 = 뺀 분)
  → 시스템 유급 분 = 근무표 합계(퇴근 − 출근 − 휴게)
- 금액: 근무표 지급(초과수당 제외) / 예상 총액(초과 기준 있을 때만) = worker_calc.pay_summary
"""
from __future__ import annotations

from datetime import date, time
import calendar

from app.services.cost_calc import effective_on
from app.services.worker_calc import day_calc, month_pay, pay_summary, recognized_in


DEFAULT_WORK_DAYS = 31


def day_bit(d: date) -> int:
    return 1 << d.weekday()            # 월=1 … 일=64


def lock_end(closed_months: list[date]) -> date | None:
    """마감된 달 중 가장 늦은 달의 말일. 이 날 이전에 시작하는 계약·계정 이력은 잠김
    (마감된 달 계산에 쓰일 수 있으므로). 마감이 없으면 None"""
    if not closed_months:
        return None
    m = max(closed_months)
    return m.replace(day=calendar.monthrange(m.year, m.month)[1])


def is_weekend(d: date) -> bool:
    """토·일 = 주말 근무 (계약 근무 요일과 무관, 지급 기준 구분용)"""
    return d.weekday() >= 5


def is_workday(rate: dict | None, d: date) -> bool:
    """그날 계약의 근무 요일인지. 시급 계약이 없으면 False (미입력 판정에서 제외)"""
    if rate is None or rate.get("pay_type") != "hourly":
        return False
    wd = rate.get("work_days")
    return bool((DEFAULT_WORK_DAYS if wd is None else int(wd)) & day_bit(d))


def work_term(w: dict) -> tuple[date | None, date | None] | None:
    """근무 대상 기간 (입사일, 퇴사일) — 양 끝 포함, None 칸 = 제한 없음.
    비활성인데 퇴사일이 없으면 None (예전 데이터: 기간을 몰라 미입력 검사 제외, 기록 있는 날만 표시)"""
    if not w.get("active") and w.get("end_date") is None:
        return None
    return w.get("start_date"), w.get("end_date")


def employed(d: date, term) -> bool:
    """그날이 근무 대상 기간 안인지"""
    if term is None:
        return False
    s, e = term
    return (s is None or d >= s) and (e is None or d <= e)


def in_term(a: date, b: date, term) -> bool:
    """기간 a~b 중 하루라도 근무 대상 기간인지"""
    if term is None:
        return False
    s, e = term
    return (s is None or s <= b) and (e is None or e >= a)


def _m(t: time | None) -> int | None:
    return None if t is None else t.hour * 60 + t.minute


def sheet_break(log_break: int | None, rate: dict) -> int:
    """근무표 '휴게' 칸 = 유급시간에서 빼는 분.
    휴게 시간 = 그날 입력값, 비우면 계약 휴게 시간. 계약이 유급 휴게면 빼지 않음 (0)"""
    b = int(rate.get("break_min") or 0) if log_break is None else int(log_break)
    return 0 if rate.get("break_paid") else b


def check_log(punch_in: time | None, clock_out: time | None, break_min: int | None, rate: dict | None,
              *, day: date, today: date, early_ok: bool = False) -> dict:
    """입력 검증 → 저장할 값 + 경고. 저장을 막는 사유는 ValueError (메시지 그대로 화면 표시)."""
    if day > today:
        raise ValueError("미래 날짜는 입력할 수 없습니다")
    if rate is None or rate.get("pay_type") != "hourly":
        raise ValueError(f"{day} 에 적용되는 시급 계약이 없습니다 (인력 > 계약 조건의 적용 시작일 확인)")
    if clock_out is None:
        raise ValueError("퇴근 시각을 입력하세요")
    ws, we = rate.get("work_start"), rate.get("work_end")
    early = bool(early_ok and punch_in is not None and ws is not None and _m(punch_in) < _m(ws))
    cin = punch_in if early else recognized_in(punch_in or ws, ws)
    span = _m(clock_out) - _m(cin)
    if span <= 0:
        raise ValueError("퇴근은 출근보다 늦어야 합니다 (자정 넘김 미지원)")
    raw = int(rate.get("break_min") or 0) if break_min is None else int(break_min)
    if raw >= span:
        raise ValueError("휴게시간이 근무시간보다 깁니다")
    warns: list[str] = []
    if span > 720:
        warns.append("근무 12시간 초과 — 시각 오기 확인")
    if we is not None and _m(clock_out) > _m(we) + 120:
        warns.append(f"지정 퇴근 {we.strftime('%H') + '시 ' + we.strftime('%M') + '분'}보다 2시간 이상 늦음")
    if punch_in is not None and ws is not None and _m(punch_in) > _m(ws) + 60:
        warns.append("지정 출근보다 1시간 이상 늦음")
    if early and _m(ws) - _m(punch_in) > 60:
        warns.append("지정 출근보다 1시간 넘게 이른 출근을 인정 — 시각 확인")
    return {"punch_in": punch_in, "clock_in": cin, "clock_out": clock_out, "break_min": break_min,
            "early_ok": early, "warns": warns}


def day_result(log: dict, rate: dict) -> dict:
    """하루 계산. paid=유급 분(근무표 합계), ot=계약 시간 밖 분, ot_pay=예상 초과수당, break=근무표 휴게 칸."""
    b = sheet_break(log.get("break_min"), rate)
    d = day_calc(log["clock_in"], log["clock_out"], break_min=b, break_paid=False,
                 work_start=rate.get("work_start"), work_end=rate.get("work_end"),
                 ot_unit_min=int(rate.get("ot_unit_min") or 0),
                 ot_unit_amount=int(rate.get("ot_unit_amount") or 0))
    return {**d, "break": b, "rate": int(rate["amount"])}


def month_summary(logs: list[dict], rates: list[dict], extras: int = 0) -> dict:
    """한 사람의 그 달 기록 + 계약 이력 전체 → 월 합계. 날짜마다 그날 적용 계약으로 계산.
    weekend_* = 토·일 근무 (기본급에는 포함, 주말 지급 기준 확인용으로 따로 표시)"""
    days, nocontract, has_rule, vat = [], 0, False, False
    wk_days = wk_min = 0
    for lg in sorted(logs, key=lambda x: x["work_date"]):
        r = effective_on(rates, lg["work_date"], "effective_from")
        if r is None or r.get("pay_type") != "hourly":
            nocontract += 1                         # 저장 뒤 계약이 바뀐 경우 → 화면에 경고
            continue
        d = day_result(lg, r)
        days.append(d)
        if is_weekend(lg["work_date"]):
            wk_days += 1
            wk_min += d["paid"]
        has_rule = has_rule or (int(r.get("ot_unit_min") or 0) > 0 and int(r.get("ot_unit_amount") or 0) > 0)
        vat = bool(r.get("vat_applied"))            # 그 달 마지막 근무일 계약 기준
    m = month_pay(days)
    return {**m, "days": len(days), "nocontract": nocontract, "weekend_days": wk_days, "weekend_min": wk_min,
            "pay": pay_summary(m["base"], m["ot_allow"], extras, vat, has_rule)}
