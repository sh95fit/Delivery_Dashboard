import { Fragment, useMemo, useState } from "react";
import type { LineupMeta, ManagerRow, StopLineup, StopPoint } from "@/api/types";
import { num, won } from "@/lib/format";

type Props = { rows: ManagerRow[]; stops: StopPoint[]; showProgress: boolean; meta: LineupMeta[] };
type Item = { id: string; label: string };

const keyOf = (m: ManagerRow) => String(m.manager_id ?? "none");
const Z = <span className="zero">-</span>;
const qtyCell = (v: number) => (v ? num(v) : Z);
const refundCell = (v: number) => (v ? <span className="neg">−{won(v)}</span> : Z);

/** 라인업 합치기 (합계 행 상세용) */
function mergeLineups(rows: ManagerRow[]) {
  const out: Record<string, StopLineup> = {};
  for (const m of rows) {
    for (const [id, v] of Object.entries(m.lineups ?? {})) {
      const d = (out[id] ??= { name: v.name, qty: 0, amount: 0, internal_qty: 0 });
      d.qty += v.qty ?? 0;
      d.amount = (d.amount ?? 0) + (v.amount ?? 0);
      d.internal_qty = (d.internal_qty ?? 0) + (v.internal_qty ?? 0);
    }
  }
  return out;
}

/** 펼침 상세: 식사별 라인업 수량·금액 */
function LineupDetail({ lineups, meta }: { lineups: Record<string, StopLineup>; meta: LineupMeta[] }) {
  const known = new Set(meta.map((x) => x.id));
  const groups: Array<{ key: string; label: string; items: Item[] }> = [
    { key: "lunch", label: "중식", items: meta.filter((x) => x.meal !== "dinner") },
    { key: "dinner", label: "석식", items: meta.filter((x) => x.meal === "dinner") },
    {
      key: "etc", label: "기타",
      items: Object.keys(lineups).filter((id) => !known.has(id)).map((id) => ({ id, label: lineups[id].name || id })),
    },
  ];

  const body = groups.flatMap((g) => {
    const items = g.items.filter((l) => (lineups[l.id]?.qty ?? 0) > 0);
    if (items.length === 0) return [];
    const q = items.reduce((a, l) => a + (lineups[l.id]?.qty ?? 0), 0);
    const amt = items.reduce((a, l) => a + (lineups[l.id]?.amount ?? 0), 0);
    return [
      ...items.map((l, i) => {
        const v = lineups[l.id];
        return (
          <tr key={`${g.key}-${l.id}`}>
            <td className="mt-meal">{i === 0 ? g.label : ""}</td>
            <td>{l.label}</td>
            <td className="num">{num(v.qty)}식</td>
            <td className="num">{won(v.amount ?? 0)}</td>
            <td className="num">{v.internal_qty ? <span className="text-internal">{num(v.internal_qty)}</span> : Z}</td>
          </tr>
        );
      }),
      <tr key={`${g.key}-sum`} className="mt-sub-sum">
        <td />
        <td>{g.label} 계</td>
        <td className="num">{num(q)}식</td>
        <td className="num">{won(amt)}</td>
        <td />
      </tr>,
    ];
  });

  if (body.length === 0) return <div className="muted small">라인업 주문이 없습니다.</div>;
  return (
    <table className="mt-sub">
      <thead>
        <tr>
          <th>구분</th><th>라인업</th><th className="num">수량</th>
          <th className="num">금액(매출−환불)</th><th className="num">직원식</th>
        </tr>
      </thead>
      <tbody>{body}</tbody>
    </table>
  );
}

export default function ManagerTable({ rows, stops, showProgress, meta }: Props) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());

  const done = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of stops) {
      if (!s.delivered_at) continue;
      const k = String(s.manager_id ?? "none");
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return m;
  }, [stops]);
  const totalLineups = useMemo(() => mergeLineups(rows), [rows]);

  const doneOf = (m: ManagerRow) => done.get(keyOf(m)) ?? 0;
  const sum = (f: (m: ManagerRow) => number) => rows.reduce((a, m) => a + f(m), 0);
  const allKeys = [...rows.map(keyOf), "__total"];
  const allOpen = allKeys.every((k) => open.has(k));
  const colCount = showProgress ? 10 : 9;

  const toggle = (k: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  const nameBtn = (k: string, label: React.ReactNode) => (
    <button type="button" className="mt-name" aria-expanded={open.has(k)} onClick={() => toggle(k)} title="라인업 상세">
      <span className="mt-caret">▸</span>
      {label}
    </button>
  );

  const detailRow = (k: string, lineups: Record<string, StopLineup>) =>
    open.has(k) && (
      <tr className="mt-detail">
        <td colSpan={colCount}><LineupDetail lineups={lineups} meta={meta} /></td>
      </tr>
    );

  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>
              매니저
              <button type="button" className="mt-all" onClick={() => setOpen(allOpen ? new Set() : new Set(allKeys))}>
                {allOpen ? "전체 접기" : "전체 펼치기"}
              </button>
            </th>
            <th className="num">배송지</th>
            {showProgress && <th className="num">완료</th>}
            <th className="num">식수</th>
            <th className="num">중식</th>
            <th className="num">석식</th>
            <th className="num">고객사</th>
            <th className="num">매출</th>
            <th className="num">환불</th>
            <th className="num">매출 − 환불</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => {
            const k = keyOf(m);
            return (
              <Fragment key={k}>
                <tr className={open.has(k) ? "mt-open" : undefined}>
                  <td>
                    {nameBtn(k, (
                      <>
                        <span className="dot" style={{ background: m.color ?? "var(--faint)" }} />
                        {m.manager_id == null ? "미배정" : m.manager_name ?? `#${m.manager_id}`}
                      </>
                    ))}
                  </td>
                  <td className="num">
                    {num(m.stops)}
                    {m.internal_stops > 0 && <span className="text-internal tag-inline">직원식 {m.internal_stops}</span>}
                  </td>
                  {showProgress && <td className="num">{num(doneOf(m))} / {num(m.stops)}</td>}
                  <td className="num">{num(m.meals)}</td>
                  <td className="num">{qtyCell(m.lunch_meals)}</td>
                  <td className="num">{qtyCell(m.dinner_meals)}</td>
                  <td className="num">{num(m.accounts)}</td>
                  <td className="num">{won(m.gross_revenue)}</td>
                  <td className="num">{refundCell(m.refund_amount)}</td>
                  <td className="num">{won(m.net_revenue)}</td>
                </tr>
                {detailRow(k, m.lineups ?? {})}
              </Fragment>
            );
          })}
          <tr className="sum">
            <td>{nameBtn("__total", "합계")}</td>
            <td className="num">{num(sum((m) => m.stops))}</td>
            {showProgress && <td className="num">{num(sum(doneOf))} / {num(sum((m) => m.stops))}</td>}
            <td className="num">{num(sum((m) => m.meals))}</td>
            <td className="num">{num(sum((m) => m.lunch_meals))}</td>
            <td className="num">{num(sum((m) => m.dinner_meals))}</td>
            <td className="num">-</td>
            <td className="num">{won(sum((m) => m.gross_revenue))}</td>
            <td className="num">{refundCell(sum((m) => m.refund_amount))}</td>
            <td className="num">{won(sum((m) => m.net_revenue))}</td>
          </tr>
          {detailRow("__total", totalLineups)}
        </tbody>
      </table>
    </div>
  );
}
