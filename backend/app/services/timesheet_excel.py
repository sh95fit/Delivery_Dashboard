"""S2-P4a 월 근무시간표 엑셀 파서·검증 (DB 없음 → 단위 테스트 대상).

양식(2026-09 물류팀 근무표): '연월' 칸 / 날짜 행(1~말일) + 요일 행 / 사람마다 4행(출근·퇴근·휴게·합계)
/ 오른쪽 월 합계 · 월급여(출근 행 = 시간, 합계 행 = 금액) · 인센티브 · 주말특별수당 · 총지급액 (+ 부가세 포함 열).
행·열 위치를 고정하지 않고 라벨로 찾는다 → 인원 추가·삭제·순서 변경, 30·31일 달 모두 같은 코드.
여기서는 엑셀 안의 일관성만 검사. 시스템 계약과의 대조는 업로드 서비스에서.
휴게 칸에 값이 있으면 합계 = 퇴근 − 출근 − 휴게 로 본다.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta

LABELS = ("출근", "퇴근", "휴게", "합계")
WEEKDAYS = "월화수목금토일"
EXCEL_EPOCH = datetime(1899, 12, 30)
PAY_HEADERS = {"월급여": "pay", "인센티브": "incentive", "주말특별수당": "weekend", "총지급액": "total"}
_T_RE = re.compile(r"^(\d{1,3})\s*([:;.])\s*(\d{2})(?:\s*:\s*(\d{2}))?$")
_T4_RE = re.compile(r"^(\d{1,2})(\d{2})$")


def hm(m: int | None) -> str:
    return "-" if m is None else f"{m // 60}:{m % 60:02d}"


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _txt(v).replace(",", "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _int(v) -> int | None:
    n = _num(v)
    return int(n) if n is not None and n == int(n) else None


def cell_minutes(v, duration: bool = False) -> tuple[int | None, str | None]:
    """셀 값 → (분 | None, 경고문 | None). 못 읽으면 ValueError."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, None
    if isinstance(v, datetime):
        if v.year <= 1900:                                   # [h]:mm 24시간 초과 표시값
            return round((v - EXCEL_EPOCH).total_seconds() / 60), None
        return v.hour * 60 + v.minute, None
    if isinstance(v, time):
        return round((v.hour * 3600 + v.minute * 60 + v.second + v.microsecond / 1e6) / 60), None
    if isinstance(v, timedelta):
        return round(v.total_seconds() / 60), None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        if not duration and f.is_integer() and 100 <= f <= 2359:
            h, m = divmod(int(f), 100)
            if m < 60:
                return h * 60 + m, f"'{int(f)}' → {h}:{m:02d}로 읽음 (콜론 누락 의심)"
            raise ValueError
        if not duration and 1 <= f < 24:
            h = int(f)
            m = round((f - h) * 100)
            if m < 60:
                return h * 60 + m, f"'{v}' → {h}:{m:02d}로 읽음 (숫자 입력 의심)"
            raise ValueError
        if 0 <= f < 50:                                      # 엑셀 시간 = 하루 비율
            return round(f * 1440), None
        raise ValueError
    s = str(v).strip().replace("：", ":")
    mt = _T_RE.match(s)
    if mt:
        h, sep, m = int(mt.group(1)), mt.group(2), int(mt.group(3))
        if m >= 60 or (not duration and h >= 24):
            raise ValueError
        warn = None if sep == ":" else f"'{s}' → {h}:{m:02d}로 읽음 (구분자 '{sep}' 오기 의심)"
        return h * 60 + m, warn
    mt = _T4_RE.match(s)
    if mt and not duration:
        h, m = int(mt.group(1)), int(mt.group(2))
        if h < 24 and m < 60:
            return h * 60 + m, f"'{s}' → {h}:{m:02d}로 읽음 (콜론 누락 의심)"
    raise ValueError


def _month(v) -> date | None:
    if isinstance(v, (datetime, date)):
        return date(v.year, v.month, 1)
    mt = re.search(r"(\d{4})\D+(\d{1,2})", _txt(v))
    if mt and 1 <= int(mt.group(2)) <= 12:
        return date(int(mt.group(1)), int(mt.group(2)), 1)
    return None


def parse_timesheet(rows, sheet_name: str = "") -> dict:
    """rows = openpyxl ws.iter_rows(values_only=True) 결과(data_only=True로 연 통합문서)."""
    rows = [list(r) if r is not None else [] for r in rows]
    issues: list[dict] = []
    out = {"sheet": sheet_name, "month": None, "people": [], "issues": issues, "ok": False}

    def add(level, msg, row=None, name=None, day=None):
        issues.append({"level": level, "msg": msg, "row": row, "name": name, "day": day})

    def cell(r, c):
        return rows[r][c] if 0 <= r < len(rows) and 0 <= c < len(rows[r]) else None

    def has(v) -> bool:
        return _txt(v) != ""

    # 1) 연월
    month = next((_month(cell(i, 1)) for i in range(min(15, len(rows))) if _txt(cell(i, 0)) == "연월"), None)
    if month is None:
        add("error", "'연월' 칸을 찾지 못했거나 읽을 수 없습니다 (A열 '연월', B열 2026-09-01)")
        return out
    out["month"] = month.isoformat()
    mdays = calendar.monthrange(month.year, month.month)[1]

    # 2) 날짜 행
    hdr = None
    for i in range(min(30, len(rows))):
        nums = [_int(v) for v in rows[i]]
        if sum(1 for n in nums if n is not None and 1 <= n <= 31) >= 28 and 1 in nums:
            hdr = i
            break
    if hdr is None:
        add("error", "날짜 행(1, 2, 3 …)을 찾지 못했습니다")
        return out
    first = next(c for c, v in enumerate(rows[hdr]) if _int(v) == 1)
    day_cols: dict[int, int] = {}
    c = first
    while _int(cell(hdr, c)) == len(day_cols) + 1:
        day_cols[c] = len(day_cols) + 1
        c += 1
    n = len(day_cols)
    if n < mdays:
        add("error", f"날짜 열이 {n}일까지만 있습니다 ({month.month}월은 {mdays}일)", row=hdr + 1)
    elif n > mdays:
        add("warn", f"날짜 열이 {n}일까지 있습니다 ({month.month}월은 {mdays}일, 이후 열은 비어 있어야 함)", row=hdr + 1)

    col: dict[str, int] = {}
    for c, v in enumerate(rows[hdr]):
        t = _txt(v)
        if t in PAY_HEADERS:
            col[PAY_HEADERS[t]] = c
        elif t == "월" and c > first:
            col["month_total"] = c
    for k, label in (("month_total", "월 합계"), ("pay", "월급여"), ("total", "총지급액")):
        if k not in col:
            add("warn", f"'{label}' 열을 찾지 못해 해당 대조를 건너뜁니다", row=hdr + 1)

    bad_wd = [d for c, d in day_cols.items()
              if d <= mdays and has(cell(hdr + 1, c))
              and _txt(cell(hdr + 1, c)) != WEEKDAYS[date(month.year, month.month, d).weekday()]]
    if bad_wd:
        add("error", f"요일 행이 {month.year}년 {month.month}월 달력과 다릅니다 "
                     f"({', '.join(map(str, bad_wd[:5]))}일 …). 연월 칸 또는 지난달 양식 복사를 확인하세요", row=hdr + 2)

    lc = next((c for i in range(hdr + 1, len(rows)) for c in range(first) if _txt(cell(i, c)) == "출근"), None)
    if lc is None:
        add("error", "'출근' 행을 찾지 못했습니다")
        return out

    seen: dict[str, int] = {}

    def person(i: int) -> dict:
        name = _txt(cell(i, 0))
        rate = _num(cell(i, 1))
        note = " / ".join(_txt(cell(i + k, 2)) for k in range(4) if has(cell(i + k, 2)))
        row, r_sum = i + 1, i + 3
        if not name:
            add("error", "이름이 비어 있습니다", row=row)
        elif name in seen:
            add("error", f"이름이 중복됩니다 ({seen[name]}행과 같음). 동명이인은 이름 뒤에 구분자를 붙이세요", row=row, name=name)
        else:
            seen[name] = row
        if rate is None or rate <= 0:
            add("error", f"시급 '{_txt(cell(i, 1))}'을(를) 읽을 수 없습니다", row=row, name=name or None)

        days: dict[int, dict] = {}
        for c, d in day_cols.items():
            vals, broken = {}, False
            for k, lab in enumerate(LABELS):
                raw = cell(i + k, c)
                try:
                    m, warn = cell_minutes(raw, duration=lab in ("휴게", "합계"))
                except ValueError:
                    add("error", f"{lab} '{_txt(raw)}'을(를) 시간으로 읽을 수 없습니다", row=i + k + 1, name=name, day=d)
                    m, warn, broken = None, None, True
                if warn:
                    add("warn", f"{lab} {warn}", row=i + k + 1, name=name, day=d)
                vals[lab] = m
            if broken:
                continue
            cin, cout, brk, tot = (vals[x] for x in LABELS)
            if d > mdays:
                if cin or cout or brk or tot:
                    add("error", f"{month.month}월에 없는 날짜에 값이 있습니다", row=row, name=name, day=d)
                continue
            if cin is None and cout is None:
                if tot or brk:
                    add("error", f"출퇴근 없이 합계·휴게 값이 있습니다 ({hm(tot or brk)})", row=r_sum + 1, name=name, day=d)
                continue
            if cin is None or cout is None:
                add("error", ("퇴근" if cout is None else "출근") + " 시각이 비어 있습니다", row=row, name=name, day=d)
                continue
            if cin >= 1440 or cout >= 1440:
                add("error", "출퇴근 시각이 24시 이상입니다", row=row, name=name, day=d)
                continue
            if cout <= cin:
                add("error", f"퇴근 {hm(cout)}이 출근 {hm(cin)}보다 빠르거나 같습니다", row=i + 2, name=name, day=d)
                continue
            span, b = cout - cin, brk or 0
            if b >= span:
                add("error", f"휴게 {hm(b)}가 근무시간 {hm(span)} 이상입니다", row=i + 3, name=name, day=d)
                continue
            mins = span - b
            if tot is None:
                add("warn", "합계 칸이 비어 있습니다 (수식 값 없음 → 엑셀에서 열어 저장 후 다시 업로드)",
                    row=r_sum + 1, name=name, day=d)
            elif tot != mins:
                add("error", f"합계 {hm(tot)} ≠ 퇴근−출근−휴게 {hm(mins)} (오기 의심)", row=r_sum + 1, name=name, day=d)
            if span > 12 * 60:
                add("warn", f"근무 {hm(span)} (12시간 초과) 확인", row=row, name=name, day=d)
            if date(month.year, month.month, d).weekday() >= 5:
                add("info", "주말 근무", row=row, name=name, day=d)
            days[d] = {"in": hm(cin), "out": hm(cout), "break_min": brk, "minutes": mins}

        total = sum(v["minutes"] for v in days.values())
        if "month_total" in col:
            raw = cell(r_sum, col["month_total"])
            try:
                mt_, _ = cell_minutes(raw, duration=True)
            except ValueError:
                mt_ = None
                add("error", f"월 합계 '{_txt(raw)}'을(를) 읽을 수 없습니다", row=r_sum + 1, name=name)
            if mt_ is not None and mt_ != total:
                add("error", f"월 합계 {hm(mt_)} ≠ 일별 합 {hm(total)}", row=r_sum + 1, name=name)

        sheet_pay = sheet_total = vat_total = None
        if "pay" in col:
            hours = _num(cell(i, col["pay"]))
            if hours is not None and abs(hours * 60 - total) > 0.5:
                add("error", f"월급여 칸 시간 {hours:.2f}h ≠ 일별 합 {total / 60:.2f}h", row=row, name=name)
            sheet_pay = _num(cell(r_sum, col["pay"]))
            if sheet_pay is not None and rate:
                exp = rate * total / 60
                if abs(sheet_pay - exp) > 1:
                    add("error", f"월급여 {sheet_pay:,.0f} ≠ 시급 × 근무시간 {exp:,.0f}", row=r_sum + 1, name=name)
        inc = _num(cell(r_sum, col["incentive"])) if "incentive" in col else None
        wk = _num(cell(r_sum, col["weekend"])) if "weekend" in col else None
        if "total" in col:
            sheet_total = _num(cell(r_sum, col["total"]))
            if sheet_total is not None:
                exp = (sheet_pay or 0) + (inc or 0) + (wk or 0)
                if abs(sheet_total - exp) > 1:
                    add("error", f"총지급액 {sheet_total:,.0f} ≠ 월급여+인센티브+주말수당 {exp:,.0f}", row=r_sum + 1, name=name)
                vat_total = _num(cell(r_sum, col["total"] + 1))
                if vat_total is not None and abs(vat_total - sheet_total * 1.1) > 1:
                    add("warn", f"총지급액 오른쪽 값 {vat_total:,.0f} ≠ 총지급액 × 1.1 ({sheet_total * 1.1:,.0f})",
                        row=r_sum + 1, name=name)
        if not days:
            add("info", "이번 달 근무 기록이 없습니다 (퇴사·휴직이면 블록 삭제 가능)", row=row, name=name or None)
        return {
            "name": name, "row": row, "rate": rate, "schedule_note": note, "days": days, "minutes": total,
            "sheet_pay": sheet_pay, "incentive": inc, "weekend": wk, "sheet_total": sheet_total,
            "vat_total": vat_total,
        }

    i = hdr + 2
    while i < len(rows):
        lab = _txt(cell(i, lc))
        if lab != "출근":
            if lab in LABELS and any(has(cell(i, c)) for c in day_cols):
                add("error", f"'{lab}' 행이 '출근' 행 없이 있습니다", row=i + 1)
            i += 1
            continue
        labs = [_txt(cell(i + k, lc)) for k in range(4)]
        if labs != list(LABELS):
            add("error", "사람마다 출근·퇴근·휴게·합계 4행이어야 합니다 (현재: "
                + "·".join(x or "빈칸" for x in labs) + ")", row=i + 1, name=_txt(cell(i, 0)) or None)
            i += 1
            while i < len(rows) and _txt(cell(i, lc)) != "출근":
                i += 1
            continue
        out["people"].append(person(i))
        i += 4

    out["ok"] = not any(x["level"] == "error" for x in issues)
    return out
