"""S2-P4c-1 인센티브 (일 단위 · 운영 계정 기준. 계정 → 사람 배정은 P4c-2).

확정 규칙 (2026-10-13)
- 제품 수 = 중식 가정식(4) + 중식 프레시밀·라이트밀(23, 29). 석식(2, 31, 30)·파일럿 가정식(21)은 참고 표시만 (집계 제외)
- 제품 수 보정 ① 배송지 제외 = 그 배송지 수량 전부 빼기 (퀵·다른 매니저 처리·미배송 등)
              ② ± 조정 = 일부만 빠지는 경우, 사유 필수
- 고객사 수 = 관리자 입력 (수거 포함). 배송지 수·주문 고객사 수는 참고. 미입력이면 고객사 인센티브 보류
- 금액 = 구간표(DB, 적용 시작일 이력) → incentive_calc
- 미지급(과실)은 데일리 인센티브만 0원. 특수 수당은 별도 합산 (미지급 영향 없음)
- 마감된 달·미래 날짜는 입력 불가
"""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import bindparam, text

from app.database import get_dash_engine, get_engine
from app.services import dash_db
from app.services.cost_calc import effective_on
from app.services.incentive_calc import check_bands, day_row
from app.services.manager_service import _iso, _rds_managers, today
from app.services.worker_service import check_unlocked

GAJUNG_IDS = (4,)
MIL_IDS = (23, 29)
DINNER_REF_IDS = (2, 31, 30)      # 석식 가정식·프레시밀·라이트밀 — 참고 표시만
PILOT_REF_IDS = (21,)             # 파일럿 가정식 — 참고 표시만
ALL_IDS = GAJUNG_IDS + MIL_IDS + DINNER_REF_IDS + PILOT_REF_IDS

EXCLUDE_REASONS = {"quick": "퀵 발송", "other_manager": "다른 매니저 처리",
                   "not_delivered": "미배송·취소", "other": "기타"}

# 배송지별 수량. 수량은 배송지 단위로 먼저 묶은 뒤 붙임 → delivery 행이 여러 개여도 수량이 두 번 잡히지 않음
SQL_STOPS = """
SELECT x.work_date, x.manager_id, x.address_id, a.name AS address_name,
       COALESCE(q.gajung_qty, 0) AS gajung_qty, COALESCE(q.mil_qty, 0) AS mil_qty,
       COALESCE(q.dinner_qty, 0) AS dinner_qty, COALESCE(q.pilot_qty, 0) AS pilot_qty,
       COALESCE(q.order_accounts, 0) AS order_accounts
FROM (
    SELECT d.date AS work_date, d.manager_id, d.address_id
    FROM delivery d
    WHERE d.date BETWEEN :s AND :e AND d.deleted_at IS NULL AND d.manager_id IS NOT NULL
    GROUP BY d.date, d.manager_id, d.address_id
) x
LEFT JOIN (
    SELECT o.delivery_date, o.address_id,
           SUM(CASE WHEN od.product_id IN :gajung THEN od.quantity ELSE 0 END) AS gajung_qty,
           SUM(CASE WHEN od.product_id IN :mil THEN od.quantity ELSE 0 END) AS mil_qty,
           SUM(CASE WHEN od.product_id IN :dinner THEN od.quantity ELSE 0 END) AS dinner_qty,
           SUM(CASE WHEN od.product_id IN :pilot THEN od.quantity ELSE 0 END) AS pilot_qty,           
           COUNT(DISTINCT o.account_id) AS order_accounts
    FROM orders o
    LEFT JOIN `order-details` od
      ON od.order_id = o.id AND od.is_refund = 0 AND od.deleted_at IS NULL AND od.product_id IN :all_ids
    WHERE o.delivery_date BETWEEN :s AND :e AND o.deleted_at IS NULL
    GROUP BY o.delivery_date, o.address_id
) q ON q.delivery_date = x.work_date AND q.address_id = x.address_id
LEFT JOIN addresses a ON a.id = x.address_id
ORDER BY x.work_date, x.manager_id, x.address_id
"""

SQL_ADJ = """
SELECT DISTINCT ON (manager_id, adj_date, field)
       id, manager_id, adj_date, field, value, reason, created_by, created_at
FROM incentive_adjustments
WHERE deleted_at IS NULL AND adj_date BETWEEN :s AND :e AND field IN ('accounts', 'product_delta')
ORDER BY manager_id, adj_date, field, created_at DESC, id DESC
"""
SQL_EXCL = """SELECT id, manager_id, work_date, address_id, reason, memo, created_by, created_at
FROM incentive_exclusions WHERE deleted_at IS NULL AND work_date BETWEEN :s AND :e"""
SQL_EXTRAS = """SELECT id, manager_id, work_date, item_id, item_name, qty, unit_amount, amount, memo,
       created_by, created_at
FROM incentive_extras WHERE deleted_at IS NULL AND work_date BETWEEN :s AND :e ORDER BY id"""
SQL_HOLDS = """SELECT id, manager_id, hold_date, reason, created_by, created_at
FROM incentive_holds WHERE released_at IS NULL AND hold_date BETWEEN :s AND :e ORDER BY id"""


# ---------- 운영 DB (RDS) ----------
def _fetch_stops(s: date, e: date) -> list[dict]:
    stmt = text(SQL_STOPS).bindparams(*(bindparam(k, expanding=True)
                                        for k in ("gajung", "mil", "dinner", "pilot", "all_ids")))
    p = {"s": s, "e": e, "gajung": list(GAJUNG_IDS), "mil": list(MIL_IDS),
         "dinner": list(DINNER_REF_IDS), "pilot": list(PILOT_REF_IDS), "all_ids": list(ALL_IDS)}
    with get_engine().connect() as conn:
        return [dict(r) for r in conn.execute(stmt, p).mappings().all()]


def _safe_fetch_stops(s: date, e: date) -> list[dict]:
    """터널 실패 시 1회 재시도 (Week 2 표준 패턴)."""
    try:
        return _fetch_stops(s, e)
    except Exception:  # noqa: BLE001
        import app.database as db
        try:
            db._get_tunnel()
        except Exception:  # noqa: BLE001
            pass
        db._engine = None
        return _fetch_stops(s, e)


def _managers() -> dict[int, dict]:
    try:
        return {m["manager_id"]: m for m in _rds_managers()}
    except Exception:  # noqa: BLE001
        return {}


# ---------- 단가표 ----------
def _rate_sets() -> list[dict]:
    sets = dash_db.rows("""SELECT id, effective_from, memo, created_by, created_at FROM incentive_rate_sets
                           WHERE deleted_at IS NULL ORDER BY effective_from""")
    bands = dash_db.rows("""SELECT b.set_id, b.kind, b.start_excl, b.end_incl, b.amount
                            FROM incentive_rate_bands b
                            JOIN incentive_rate_sets s ON s.id = b.set_id AND s.deleted_at IS NULL
                            ORDER BY b.set_id, b.kind, b.start_excl""")
    by: dict[int, dict] = {}
    for b in bands:
        by.setdefault(b["set_id"], {"product": [], "account": []})[b["kind"]].append(
            {"start": int(b["start_excl"]), "end": None if b["end_incl"] is None else int(b["end_incl"]),
             "amount": int(b["amount"])})
    for s in sets:
        s["bands"] = by.get(s["id"], {"product": [], "account": []})
    return sets


def _set_out(s: dict) -> dict:
    return {"id": s["id"], "effective_from": _iso(s["effective_from"]), "memo": s.get("memo"),
            "created_by": s.get("created_by"), "bands": s["bands"]}


def list_rate_sets() -> dict:
    sets = _rate_sets()
    cur = effective_on(sets, today(), "effective_from")
    return {"items": [{**_set_out(s), "current": cur is not None and s["id"] == cur["id"]} for s in reversed(sets)]}


def save_rate_set(sid: int | None, body: dict, email: str) -> dict:
    """새 단가표 추가(sid=None) 또는 수정(= 기존 삭제 표시 + 새로 저장, 이력 보존)."""
    prod = check_bands("product", body["product"])
    acc = check_bands("account", body["account"])
    f = body["effective_from"]
    with get_dash_engine().begin() as conn:
        check_unlocked(conn, f, "인센티브 단가 이력")
        if sid is not None:
            old = conn.execute(text("SELECT effective_from FROM incentive_rate_sets WHERE id = :i AND deleted_at IS NULL"),
                               {"i": sid}).first()
            if not old:
                raise ValueError("단가표를 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
            check_unlocked(conn, old[0], "인센티브 단가 이력")
            conn.execute(text("UPDATE incentive_rate_sets SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                         {"i": sid, "e": email})
        if conn.execute(text("SELECT 1 FROM incentive_rate_sets WHERE effective_from = :f AND deleted_at IS NULL"),
                        {"f": f}).first():
            raise ValueError(f"{f}에 시작하는 단가표가 이미 있습니다. 그 단가표를 수정하세요")
        new_id = int(conn.execute(text("""INSERT INTO incentive_rate_sets (effective_from, memo, created_by)
                                          VALUES (:f, :m, :e) RETURNING id"""),
                                  {"f": f, "m": body.get("memo"), "e": email}).scalar_one())
        for kind, rows in (("product", prod), ("account", acc)):
            for b in rows:
                conn.execute(text("""INSERT INTO incentive_rate_bands (set_id, kind, start_excl, end_incl, amount)
                                     VALUES (:s, :k, :a, :b, :m)"""),
                             {"s": new_id, "k": kind, "a": b["start"], "b": b["end"], "m": b["amount"]})
    return {"ok": True, "id": new_id}


def delete_rate_set(sid: int, email: str) -> dict:
    with get_dash_engine().begin() as conn:
        old = conn.execute(text("SELECT effective_from FROM incentive_rate_sets WHERE id = :i AND deleted_at IS NULL"),
                           {"i": sid}).first()
        if not old:
            raise ValueError("단가표를 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
        n = conn.execute(text("SELECT COUNT(*) FROM incentive_rate_sets WHERE deleted_at IS NULL")).scalar_one()
        if n <= 1:
            raise ValueError("단가표가 하나뿐이라 삭제할 수 없습니다. 수정으로 바꾸세요")
        check_unlocked(conn, old[0], "인센티브 단가 이력")
        conn.execute(text("UPDATE incentive_rate_sets SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                     {"i": sid, "e": email})
    return {"ok": True}


# ---------- 조립 ----------
def _excl_out(x: dict) -> dict:
    return {"id": x["id"], "address_id": int(x["address_id"]), "reason": x["reason"],
            "reason_label": EXCLUDE_REASONS.get(x["reason"], x["reason"]), "memo": x.get("memo"),
            "created_by": x.get("created_by"), "created_at": _iso(x.get("created_at"))}


def _extra_out(x: dict) -> dict:
    return {"id": x["id"], "item_id": x["item_id"], "item_name": x["item_name"], "qty": int(x["qty"]),
            "unit_amount": int(x["unit_amount"]), "amount": int(x["amount"]), "memo": x.get("memo"),
            "created_by": x.get("created_by"), "created_at": _iso(x.get("created_at"))}


def _adj_out(a: dict | None) -> dict | None:
    if not a:
        return None
    return {"value": int(a["value"]), "reason": a.get("reason"), "created_by": a.get("created_by"),
            "created_at": _iso(a.get("created_at"))}


def _build(s: date, e: date, *, detail: bool) -> dict[tuple[date, int], dict]:
    stops = _safe_fetch_stops(s, e)
    p = {"s": s, "e": e}
    adj, excl = dash_db.rows(SQL_ADJ, p), dash_db.rows(SQL_EXCL, p)
    extras, holds = dash_db.rows(SQL_EXTRAS, p), dash_db.rows(SQL_HOLDS, p)
    sets = _rate_sets()

    by_stop: dict = {}
    for r in stops:
        by_stop.setdefault((r["work_date"], int(r["manager_id"])), []).append(r)
    by_adj: dict = {}
    for r in adj:
        by_adj.setdefault((r["adj_date"], int(r["manager_id"])), {})[r["field"]] = r
    by_excl: dict = {}
    for r in excl:
        by_excl.setdefault((r["work_date"], int(r["manager_id"])), {})[int(r["address_id"])] = r
    by_extra: dict = {}
    for r in extras:
        by_extra.setdefault((r["work_date"], int(r["manager_id"])), []).append(r)
    by_hold: dict = {}
    for r in holds:
        by_hold.setdefault((r["hold_date"], int(r["manager_id"])), []).append(r)

    # 같은 날 같은 배송지를 '제외하지 않은' 계정이 2곳 이상 → 수량 중복 경고
    holders: dict = {}
    for (d, mid), lst in by_stop.items():
        ex = by_excl.get((d, mid), {})
        for st in lst:
            aid = int(st["address_id"])
            if aid not in ex:
                holders.setdefault((d, aid), set()).add(mid)
    shared: dict = {}
    for (d, aid), ms in holders.items():
        if len(ms) > 1:
            shared.setdefault(d, set()).add(aid)

    out: dict = {}
    for k in set(by_stop) | set(by_adj) | set(by_excl) | set(by_extra) | set(by_hold):
        d, _mid = k
        rs = effective_on(sets, d, "effective_from")
        a, ex = by_adj.get(k, {}), by_excl.get(k, {})
        xs, hs, lst = by_extra.get(k, []), by_hold.get(k, []), by_stop.get(k, [])
        sh = shared.get(d, set())
        row = day_row(lst, ex,
                      int(a["product_delta"]["value"]) if "product_delta" in a else 0,
                      int(a["accounts"]["value"]) if "accounts" in a else None,
                      rs["bands"] if rs else None, bool(hs), sum(int(x["amount"]) for x in xs), sh)
        row["order_accounts"] = sum(int(st.get("order_accounts") or 0) for st in lst)
        if detail:
            row["stop_list"] = [{
                "address_id": int(st["address_id"]), "address_name": st.get("address_name"),
                "gajung_qty": int(st.get("gajung_qty") or 0), "mil_qty": int(st.get("mil_qty") or 0),
                "dinner_qty": int(st.get("dinner_qty") or 0), "order_accounts": int(st.get("order_accounts") or 0),
                "pilot_qty": int(st.get("pilot_qty") or 0),                
                "shared": int(st["address_id"]) in sh,
                "exclusion": _excl_out(ex[int(st["address_id"])]) if int(st["address_id"]) in ex else None,
            } for st in lst]
            row["exclusions"] = [_excl_out(x) for x in ex.values()]
            row["extra_list"] = [_extra_out(x) for x in xs]
            row["hold_list"] = [{"id": h["id"], "reason": h["reason"], "created_by": h.get("created_by"),
                                 "created_at": _iso(h.get("created_at"))} for h in hs]
            row["accounts_info"] = _adj_out(a.get("accounts"))
            row["delta_info"] = _adj_out(a.get("product_delta"))
        out[k] = row
    return out


def _closed(d: date) -> bool:
    return bool(dash_db.rows("SELECT 1 FROM month_closings WHERE month = :m AND reopened_at IS NULL",
                             {"m": d.replace(day=1)}))


def _named(mid: int, r: dict, mgrs: dict) -> dict:
    m = mgrs.get(mid) or {}
    return {"manager_id": mid, "manager_name": m.get("name") or f"계정 {mid}", "color": m.get("color"), **r}


def day_view(d: date) -> dict:
    rows = _build(d, d, detail=True)
    mgrs = _managers()
    items = [_named(mid, r, mgrs) for (_d, mid), r in rows.items()]
    items.sort(key=lambda x: (x["stops"] == 0, x["manager_name"]))
    rs = effective_on(_rate_sets(), d, "effective_from")
    return {
        "date": d.isoformat(), "closed": _closed(d), "future": d > today(),
        "rate": _set_out(rs) if rs else None,
        "extra_items": [i for i in list_extra_items()["items"] if i["active"]],
        "exclude_reasons": EXCLUDE_REASONS,
        "items": items,
        "totals": {
            "payable": sum(i["payable"] or 0 for i in items), "extras": sum(i["extras"] for i in items),
            "total": sum(i["total"] for i in items),
            "need_accounts": sum(1 for i in items if i["status"] == "need_accounts"),
            "held": sum(1 for i in items if i["status"] == "held"),
        },
    }


def month_board(month: date) -> dict:
    s = month.replace(day=1)
    last = calendar.monthrange(s.year, s.month)[1]
    rows = _build(s, s.replace(day=last), detail=False)
    mgrs, t = _managers(), today()
    people: dict[int, dict] = {}
    for (d, mid), r in rows.items():
        p = people.setdefault(mid, {**_named(mid, {}, mgrs), "days": {}, "sum": {
            "incentive": 0, "extras": 0, "total": 0, "work_days": 0, "held_days": 0,
            "pending_days": 0, "warn_days": 0}})
        p["days"][str(d.day)] = {k: r[k] for k in ("payable", "extras", "total", "status", "product_total",
                                                  "accounts", "stops")} | {"warn": bool(r["warns"])}
        sm = p["sum"]
        sm["incentive"] += r["payable"] or 0
        sm["extras"] += r["extras"]
        sm["total"] += r["total"]
        sm["work_days"] += 1 if r["stops"] else 0
        sm["held_days"] += 1 if r["status"] == "held" else 0
        sm["pending_days"] += 1 if r["status"] == "need_accounts" and d <= t else 0
        sm["warn_days"] += 1 if r["warns"] else 0
    ps = sorted(people.values(), key=lambda x: x["manager_name"])
    return {"month": s.isoformat(), "last_day": last, "closed": _closed(s), "people": ps,
            "totals": {k: sum(p["sum"][k] for p in ps) for k in ("incentive", "extras", "total", "pending_days")}}


# ---------- 입력 (관리자) ----------
def _check_open(conn, d: date) -> None:
    if d > today():
        raise ValueError("미래 날짜는 입력할 수 없습니다")
    if conn.execute(text("SELECT 1 FROM month_closings WHERE month = :m AND reopened_at IS NULL"),
                    {"m": d.replace(day=1)}).first():
        raise ValueError(f"{d.year}년 {d.month}월은 마감되었습니다. 근무 기록 > 월 표 > 마감 관리에서 해제 후 수정하세요")


def _clear_adj(conn, mid: int, d: date, field: str, email: str) -> int:
    return conn.execute(text("""UPDATE incentive_adjustments SET deleted_at = NOW(), deleted_by = :e
                                WHERE manager_id = :m AND adj_date = :d AND field = :f AND deleted_at IS NULL"""),
                        {"m": mid, "d": d, "f": field, "e": email}).rowcount


def _insert_adj(conn, mid: int, d: date, field: str, value: int, reason: str | None, email: str) -> None:
    conn.execute(text("""INSERT INTO incentive_adjustments (manager_id, adj_date, field, value, reason, created_by)
                         VALUES (:m, :d, :f, :v, :r, :e)"""),
                 {"m": mid, "d": d, "f": field, "v": value, "r": reason, "e": email})


def save_accounts(d: date, items: list[dict], email: str) -> dict:
    """하루 × 여러 계정 고객사 수. value=None → 입력 지우기 (이력은 삭제 표시로 보존)."""
    ids = [int(i["manager_id"]) for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("같은 계정이 두 번 들어 있습니다")
    saved = cleared = unchanged = 0
    with get_dash_engine().begin() as conn:
        _check_open(conn, d)
        cur = {int(r[0]): int(r[1]) for r in conn.execute(text("""
            SELECT DISTINCT ON (manager_id) manager_id, value FROM incentive_adjustments
            WHERE deleted_at IS NULL AND adj_date = :d AND field = 'accounts'
            ORDER BY manager_id, created_at DESC, id DESC"""), {"d": d}).fetchall()}
        for it in items:
            mid, v = int(it["manager_id"]), it.get("value")
            old = cur.get(mid)
            if v is None:
                if old is None:
                    unchanged += 1
                else:
                    _clear_adj(conn, mid, d, "accounts", email)
                    cleared += 1
            elif old == int(v):
                unchanged += 1
            else:
                _clear_adj(conn, mid, d, "accounts", email)
                _insert_adj(conn, mid, d, "accounts", int(v), None, email)
                saved += 1
    return {"ok": True, "saved": saved, "cleared": cleared, "unchanged": unchanged}


def set_delta(d: date, mid: int, value: int, reason: str | None, email: str) -> dict:
    """제품 수 ± 조정 (일부만 빠지는 경우). 0 = 조정 지우기."""
    reason = (reason or "").strip() or None
    if value != 0 and not reason:
        raise ValueError("제품 수 조정은 사유를 입력하세요 (예 — 퀵으로 일부 3개 발송)")
    with get_dash_engine().begin() as conn:
        _check_open(conn, d)
        _clear_adj(conn, mid, d, "product_delta", email)
        if value != 0:
            _insert_adj(conn, mid, d, "product_delta", int(value), reason, email)
    return {"ok": True}


def add_exclusion(body: dict, email: str) -> dict:
    d, mid, aid = body["work_date"], int(body["manager_id"]), int(body["address_id"])
    if not any(int(r["manager_id"]) == mid and int(r["address_id"]) == aid for r in _safe_fetch_stops(d, d)):
        raise ValueError("그날 이 계정에 배정된 배송지가 아닙니다 (새로고침 후 다시 선택하세요)")
    with get_dash_engine().begin() as conn:
        _check_open(conn, d)
        if conn.execute(text("""SELECT 1 FROM incentive_exclusions WHERE manager_id = :m AND work_date = :d
                                AND address_id = :a AND deleted_at IS NULL"""),
                        {"m": mid, "d": d, "a": aid}).first():
            raise ValueError("이미 제외된 배송지입니다")
        xid = conn.execute(text("""INSERT INTO incentive_exclusions
                                   (manager_id, work_date, address_id, reason, memo, created_by)
                                   VALUES (:m, :d, :a, :r, :memo, :e) RETURNING id"""),
                           {"m": mid, "d": d, "a": aid, "r": body["reason"], "memo": body.get("memo"),
                            "e": email}).scalar_one()
    return {"ok": True, "id": int(xid)}


def delete_exclusion(xid: int, email: str) -> dict:
    with get_dash_engine().begin() as conn:
        r = conn.execute(text("SELECT work_date FROM incentive_exclusions WHERE id = :i AND deleted_at IS NULL"),
                         {"i": xid}).first()
        if not r:
            raise ValueError("제외 기록을 찾을 수 없습니다 (이미 해제됨 — 새로고침하세요)")
        _check_open(conn, r[0])
        conn.execute(text("UPDATE incentive_exclusions SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                     {"i": xid, "e": email})
    return {"ok": True}


# ---------- 특수 수당 (인센티브 미지급과 무관) ----------
def list_extra_items() -> dict:
    rows = dash_db.rows("""SELECT id, name, unit_amount, active, sort_order, memo FROM incentive_extra_items
                           ORDER BY active DESC, sort_order, name""")
    return {"items": [{"id": r["id"], "name": r["name"],
                       "unit_amount": None if r["unit_amount"] is None else int(r["unit_amount"]),
                       "active": bool(r["active"]), "sort_order": int(r["sort_order"]), "memo": r.get("memo")}
                      for r in rows]}


def save_extra_item(iid: int | None, body: dict, email: str) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("품목 이름을 입력하세요")
    p = {"n": name, "u": body.get("unit_amount"), "a": bool(body.get("active", True)),
         "s": int(body.get("sort_order") or 0), "m": body.get("memo"), "e": email, "i": iid or 0}
    with get_dash_engine().begin() as conn:
        if conn.execute(text("SELECT 1 FROM incentive_extra_items WHERE name = :n AND id <> :i"), p).first():
            raise ValueError(f"'{name}' 품목이 이미 있습니다 (사용 안 함 상태일 수 있습니다 — 목록에서 다시 켜세요)")
        if iid is None:
            new_id = conn.execute(text("""INSERT INTO incentive_extra_items
                                          (name, unit_amount, active, sort_order, memo, created_by)
                                          VALUES (:n, :u, :a, :s, :m, :e) RETURNING id"""), p).scalar_one()
            return {"ok": True, "id": int(new_id)}
        res = conn.execute(text("""UPDATE incentive_extra_items SET name = :n, unit_amount = :u, active = :a,
                                   sort_order = :s, memo = :m, updated_by = :e, updated_at = NOW() WHERE id = :i"""), p)
        if res.rowcount == 0:
            raise ValueError("품목을 찾을 수 없습니다")
    return {"ok": True, "id": iid}


def _insert_extra(conn, mid: int, d: date, item: dict, qty: int, unit: int, memo: str | None, email: str) -> int:
    if conn.execute(text("""SELECT 1 FROM incentive_extras WHERE manager_id = :m AND work_date = :d
                            AND item_id = :i AND deleted_at IS NULL"""), {"m": mid, "d": d, "i": item["id"]}).first():
        raise ValueError(f"{d} '{item['name']}'이(가) 이미 등록되어 있습니다. 건수를 늘리려면 기존 행을 수정하세요")
    return int(conn.execute(text("""INSERT INTO incentive_extras
            (manager_id, work_date, item_id, item_name, qty, unit_amount, amount, memo, created_by)
            VALUES (:m, :d, :i, :n, :q, :u, :a, :memo, :e) RETURNING id"""),
        {"m": mid, "d": d, "i": item["id"], "n": item["name"], "q": qty, "u": unit, "a": qty * unit,
         "memo": memo, "e": email}).scalar_one())


def _unit_warn(item: dict, unit: int) -> list[str]:
    base = item.get("unit_amount")
    return [f"기본 금액 {int(base):,}원과 다른 금액({unit:,}원)으로 저장했습니다"] if base and int(base) != unit else []


def add_extra(body: dict, email: str) -> dict:
    d, mid = body["work_date"], int(body["manager_id"])
    with get_dash_engine().begin() as conn:
        _check_open(conn, d)
        item = conn.execute(text("SELECT id, name, unit_amount, active FROM incentive_extra_items WHERE id = :i"),
                            {"i": body["item_id"]}).mappings().first()
        if not item or not item["active"]:
            raise ValueError("사용할 수 없는 품목입니다 (특수 수당 품목 목록 확인)")
        unit = body.get("unit_amount") or item["unit_amount"]
        if not unit:
            raise ValueError(f"'{item['name']}' 품목은 기본 금액이 없어 금액을 입력해야 합니다")
        xid = _insert_extra(conn, mid, d, dict(item), int(body["qty"]), int(unit), body.get("memo"), email)
    return {"ok": True, "id": xid, "warns": _unit_warn(dict(item), int(unit))}


def update_extra(xid: int, body: dict, email: str) -> dict:
    """수정 = 기존 행 삭제 표시 + 새 행 (이력 보존)"""
    with get_dash_engine().begin() as conn:
        old = conn.execute(text("""SELECT x.manager_id, x.work_date, x.item_id, x.item_name, i.unit_amount
                                   FROM incentive_extras x JOIN incentive_extra_items i ON i.id = x.item_id
                                   WHERE x.id = :i AND x.deleted_at IS NULL"""), {"i": xid}).mappings().first()
        if not old:
            raise ValueError("특수 수당 기록을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
        _check_open(conn, old["work_date"])
        conn.execute(text("""UPDATE incentive_extras SET deleted_at = NOW(), deleted_by = :e, delete_reason = '수정'
                             WHERE id = :i"""), {"i": xid, "e": email})
        item = {"id": old["item_id"], "name": old["item_name"], "unit_amount": old["unit_amount"]}
        unit = int(body.get("unit_amount") or old["unit_amount"] or 0)
        if unit <= 0:
            raise ValueError("금액을 입력하세요")
        new_id = _insert_extra(conn, int(old["manager_id"]), old["work_date"], item,
                               int(body["qty"]), unit, body.get("memo"), email)
    return {"ok": True, "id": new_id, "warns": _unit_warn(item, unit)}


def delete_extra(xid: int, reason: str, email: str) -> dict:
    with get_dash_engine().begin() as conn:
        r = conn.execute(text("SELECT work_date FROM incentive_extras WHERE id = :i AND deleted_at IS NULL"),
                         {"i": xid}).first()
        if not r:
            raise ValueError("특수 수당 기록을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
        _check_open(conn, r[0])
        conn.execute(text("""UPDATE incentive_extras SET deleted_at = NOW(), deleted_by = :e, delete_reason = :r
                             WHERE id = :i"""), {"i": xid, "e": email, "r": reason})
    return {"ok": True}


# ---------- 미지급 (데일리 인센티브만 0원, 하루 여러 건) ----------
def add_hold(d: date, mid: int, reason: str, email: str) -> dict:
    with get_dash_engine().begin() as conn:
        _check_open(conn, d)
        hid = conn.execute(text("""INSERT INTO incentive_holds (manager_id, hold_date, reason, created_by)
                                   VALUES (:m, :d, :r, :e) RETURNING id"""),
                           {"m": mid, "d": d, "r": reason, "e": email}).scalar_one()
    return {"ok": True, "id": int(hid)}


def release_hold(hid: int, reason: str, email: str) -> dict:
    with get_dash_engine().begin() as conn:
        r = conn.execute(text("SELECT hold_date FROM incentive_holds WHERE id = :i AND released_at IS NULL"),
                         {"i": hid}).first()
        if not r:
            raise ValueError("미지급 기록을 찾을 수 없습니다 (이미 해제됨 — 새로고침하세요)")
        _check_open(conn, r[0])
        conn.execute(text("""UPDATE incentive_holds SET released_at = NOW(), released_by = :e, release_reason = :r
                             WHERE id = :i"""), {"i": hid, "e": email, "r": reason})
    return {"ok": True}
