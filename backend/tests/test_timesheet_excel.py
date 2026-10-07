from datetime import date, datetime, time, timedelta

from app.services.timesheet_excel import cell_minutes, parse_timesheet, schedule_ranges

W = {1: (time(7), "13:13"), 2: (time(7), time(13, 10)), 3: ("07:00", "13:02:00")}


def _m(v):
    return cell_minutes(v)[0]


def block(name, rate, work, ndays=30, extra=()):
    ins, outs = [None] * ndays, [None] * ndays
    for d, (a, b) in work.items():
        ins[d - 1], outs[d - 1] = a, b
    mins = [(_m(outs[k]) - _m(ins[k])) if ins[k] is not None else 0 for k in range(ndays)]
    total = sum(mins)
    pay = rate * total / 60
    return [
        [name, rate, "07:00~13:00", "출근", *ins, None, None, total / 60],
        [None, None, None, "퇴근", *outs],
        [None, None, None, "휴게", *([None] * ndays)],
        [None, None, None, "합계", *[timedelta(minutes=x) for x in mins],
         f"{total // 60}:{total % 60:02d}", None, pay, None, None, pay, *extra],
    ]


def sheet(*blocks, month=date(2026, 9, 1), ndays=30):
    days = list(range(1, ndays + 1))
    wd = ["월화수목금토일"[date(month.year, month.month, d).weekday()] for d in days]
    rows = [["공장", "테스트공장"], ["부서", "물류팀"], ["연월", datetime(month.year, month.month, 1)], [],
            [None] * 4 + days + ["월", None, "월급여", "인센티브", "주말특별수당", "총지급액"],
            [None] * 4 + wd + ["합계"],
            ["성명", "시급", "시간대", "구분"]]
    for b in blocks:
        rows.extend(b)
    return rows


def msgs(res, level="error"):
    return [x["msg"] for x in res["issues"] if x["level"] == level]


def test_valid_sheet_mixed_cell_types():
    res = parse_timesheet(sheet(block("인력B", 16000, W), block("인력G", 27500, {1: (time(7), "13:45")})))
    assert res["ok"], msgs(res)
    assert res["month"] == "2026-09-01"
    p = res["people"][0]
    assert p["minutes"] == 373 + 370 + 362 and p["days"][1]["out"] == "13:13"


def test_typos_detected():
    b = block("인력B", 16000, W)
    b[1][4] = "13;13"                                  # 1일 퇴근 구분자 오기
    b[1][5] = "25:10"                                  # 2일 퇴근 읽기 실패
    b[3][6] = timedelta(hours=6, minutes=12)           # 3일 합계 오기 (실제 6:02)
    res = parse_timesheet(sheet(b))
    assert not res["ok"]
    assert any("구분자" in m for m in msgs(res, "warn"))
    assert any("25:10" in m for m in msgs(res))
    assert any("오기 의심" in m for m in msgs(res))


def test_people_added_removed_and_broken_block():
    broken = block("인력J", 15000, {17: (time(8), time(13, 10))})
    del broken[2]                                      # 휴게 행 삭제
    res = parse_timesheet(sheet(block("인력B", 16000, W), broken, block("인력E", 15000, {1: (time(8), "13:15")})))
    assert [p["name"] for p in res["people"]] == ["인력B", "인력E"]
    assert any("4행" in m for m in msgs(res))
    res2 = parse_timesheet(sheet(block("인력E", 15000, {1: (time(8), "13:15")})))
    assert res2["ok"] and [p["name"] for p in res2["people"]] == ["인력E"]


def test_duplicate_name():
    res = parse_timesheet(sheet(block("인력B", 16000, W), block("인력B", 16000, W)))
    assert any("중복" in m for m in msgs(res))


def test_month_mismatch():
    rows = sheet(block("인력B", 16000, W))
    rows[2][1] = datetime(2026, 10, 1)                 # 9월 양식에 10월 연월
    errs = msgs(parse_timesheet(rows))
    assert any("요일" in m for m in errs) and any("31일" in m for m in errs)


def test_pay_and_vat_columns():
    b = block("인력H", 27500, {1: (time(6, 30), "13:58")}, extra=[None])
    pay = 27500 * 448 / 60
    b[3][-1] = round(pay * 1.1)
    assert parse_timesheet(sheet(b))["ok"]
    b[3][36] = pay + 10000                             # 월급여 오기
    assert any(m.startswith("월급여") for m in msgs(parse_timesheet(sheet(b))))


def test_schedule_ranges():
    assert schedule_ranges("07:00~13:00") == [("07:00", "13:00")]
    assert schedule_ranges("600~13:00") == [("06:00", "13:00")]
    assert schedule_ranges("6:00 - 13:00") == [("06:00", "13:00")]
    assert schedule_ranges("07:00~12:30 / 9/8~ 07:00~13:30") == [("07:00", "12:30"), ("07:00", "13:30")]
    assert schedule_ranges("13:00~07:00") == []
    assert schedule_ranges(None) == []
