"""S2-P4a-1 근무 기록 검증·계산 순수 함수 (DB 없음 → 단위 테스트 대상).

- 출근: 지문 시각(punch_in) → 인정 출근(clock_in). 비우면 지정 출근
- 휴게(근무표 '휴게' 칸 = 합계에서 빼는 분): 직접 입력값, 비우면 계약 무급 휴게 (유급이면 0)
  → 시스템 유급 분 = 근무표 합계(퇴근 − 출근 − 휴게)
- 금액: 근무표 지급(초과수당 제외) / 예상 총액(초과 기준 있을 때만) = worker_calc.pay_summary
"""
from __future__ import annotations

from datetime import date, time

from app.services.cost_calc import effective_on
from app.services.worker_calc import day_calc, month_pay, pay_summary, recognized_in


def _m(t: time | None) -> int | None:
    return None if t is None else t.hour * 60 + t.minute


def sheet_break(log_break: int | None, rate: dict) -> int:
    if log_break is not None:
        return int(log_break)
    return 0 if rate.get("break_paid") else int(rate.get("break_min") or 0)


def check_log(punch_in: time | None, clock_out: time | None, break_min: int | None, rate: dict | None,
              *, day: date, today: date) -> dict:
    """입력 검증 → 저장할 값 + 경고. 저장을 막는 사유는 ValueError (메시지 그대로 화면 표시)."""
    if day > today:
        raise ValueError("미래 날짜는 입력할 수 없습니다")
    if rate is None or rate.get("pay_type") != "hourly":
        raise ValueError(f"{day} 에 적용되는 시급 계약이 없습니다 (인력 > 계약 조건의 적용 시작일 확인)")
    if clock_out is None:
        raise ValueError("퇴근 시각을 입력하세요")
    ws, we = rate.get("work_start"), rate.get("work_end")
    cin = recognized_in(punch_in or ws, ws)
    span = _m(clock_out) - _m(cin)
    if span <= 0:
        raise ValueError("퇴근은 출근보다 늦어야 합니다 (자정 넘김 미지원)")
    if sheet_break(break_min, rate) >= span:
        raise ValueError("휴게시간이 근무시간보다 깁니다")
    warns: list[str] = []
    if span > 720:
        warns.append("근무 12시간 초과 — 시각 오기 확인")
    if we is not None and _m(clock_out) > _m(we) + 120:
        warns.append(f"지정 퇴근 {we.strftime('%H') + '시 ' + we.strftime('%M') + '분'}보다 2시간 이상 늦음")
    if punch_in is not None and ws is not None and _m(punch_in) > _m(ws) + 60:
        warns.append("지정 출근보다 1시간 이상 늦음")
    return {"punch_in": punch_in, "clock_in": cin, "clock_out": clock_out, "break_min": break_min, "warns": warns}


def day_result(log: dict, rate: dict) -> dict:
    """하루 계산. paid=유급 분(근무표 합계), ot=계약 시간 밖 분, ot_pay=예상 초과수당, break=근무표 휴게 칸."""
    b = sheet_break(log.get("break_min"), rate)
    d = day_calc(log["clock_in"], log["clock_out"], break_min=b, break_paid=False,
                 work_start=rate.get("work_start"), work_end=rate.get("work_end"),
                 ot_unit_min=int(rate.get("ot_unit_min") or 0),
                 ot_unit_amount=int(rate.get("ot_unit_amount") or 0))
    return {**d, "break": b, "rate": int(rate["amount"])}


def month_summary(logs: list[dict], rates: list[dict], extras: int = 0) -> dict:
    """한 사람의 그 달 기록 + 계약 이력 전체 → 월 합계. 날짜마다 그날 적용 계약으로 계산."""
    days, nocontract, has_rule, vat = [], 0, False, False
    for lg in sorted(logs, key=lambda x: x["work_date"]):
        r = effective_on(rates, lg["work_date"], "effective_from")
        if r is None or r.get("pay_type") != "hourly":
            nocontract += 1                         # 저장 뒤 계약이 바뀐 경우 → 화면에 경고
            continue
        days.append(day_result(lg, r))
        has_rule = has_rule or (int(r.get("ot_unit_min") or 0) > 0 and int(r.get("ot_unit_amount") or 0) > 0)
        vat = bool(r.get("vat_applied"))            # 그 달 마지막 근무일 계약 기준
    m = month_pay(days)
    return {**m, "days": len(days), "nocontract": nocontract,
            "pay": pay_summary(m["base"], m["ot_allow"], extras, vat, has_rule)}
