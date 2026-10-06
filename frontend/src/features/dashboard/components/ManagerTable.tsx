import { Fragment, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { LineupMeta, ManagerRow, StopLineup, StopPoint } from "@/api/types";
import { num, won } from "@/lib/format";

type Props = { rows: ManagerRow[]; stops: StopPoint[]; showProgress: boolean; meta: LineupMeta[] };
type Item = { id: string; label: string };

const TOTAL = "__total";
const keyOf = (m: ManagerRow) => String(m.manager_id ?? "none");
const Z = <span className="zero">-</span>;
const qtyCell = (v: number) => (v ? num(v) : Z);
const refundCell = (v: number) => (v ? <span className="neg">−{won(v)}</span> : Z);

const Chevron = () => (
  <svg className="mt-caret" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

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

/** 펼침 상세: 식사별 라인업 카드 (수량·금액·비중) */
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

  const blocks = groups.flatMap((g) => {
    const items = g.items.filter((l) => (lineups[l.id]?.qty ?? 0) > 0);
    if (items.length === 0) return [];
    const q = items.reduce((a, l) => a + (lineups[l.id]?.qty ?? 0), 0);
    const amt = items.reduce((a, l) => a + (lineups[l.id]?.amount ?? 0), 0);
    return [
      <div className="ld-row" key={g.key}>
        <div className="ld-meal">{g.label}</div>
        <div className="ld-cards">
          {items.map((l) => {
            const v = lineups[l.id];
            return (
              <div className="ld-card" key={l.id}>
                <div className="ld-name">{l.label}<span className="ld-pct">{q ? Math.round((v.qty / q) * 100) : 0}%</span></div>
                <div className="ld-qty">{num(v.qty)}<small>식</small></div>
                <div className="ld-amt">{won(v.amount ?? 0)}</div>
                {v.internal_qty ? <div className="ld-int">직원식 {num(v.internal_qty)}</div> : null}
              </div>
            );
          })}
          <div className="ld-card ld-total">
            <div className="ld-name">{g.label} 계</div>
            <div className="ld-qty">{num(q)}<small>식</small></div>
            <div className="ld-amt">{won(amt)}</div>
          </div>
        </div>
      </div>,
    ];
  });

  return blocks.length ? <div className="ld">{blocks}</div> : <div className="muted small">라인업 주문이 없습니다.</div>;
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
  const allKeys = [...rows.map(keyOf), TOTAL];
  const allOpen = allKeys.every((k) => open.has(k));
  const colCount = showProgress ? 10 : 9;

  const toggle = (k: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  // 버튼에는 onClick 없음 → 클릭·Enter 모두 행(tr)의 onClick 한 번으로 처리
  const nameBtn = (k: string, label: ReactNode) => (
    <button type="button" className="mt-name" aria-expanded={open.has(k)} title="라인업 상세">
      <Chevron />
      {label}
    </button>
  );

  const rowProps = (k: string, extra = "") => ({
    className: `mt-row${open.has(k) ? " mt-open" : ""}${extra}`,
    onClick: () => toggle(k),
  });

  const detailRow = (k: string, lineups: Record<string, StopLineup>, color?: string | null) =>
    open.has(k) && (
      <tr className="mt-detail">
        <td colSpan={colCount} style={{ "--c": color ?? "#cbd5e1" } as CSSProperties}>
          <LineupDetail lineups={lineups} meta={meta} />
        </td>
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
                <tr {...rowProps(k)}>
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
                {detailRow(k, m.lineups ?? {}, m.color)}
              </Fragment>
            );
          })}
          <tr {...rowProps(TOTAL, " sum")}>
            <td>{nameBtn(TOTAL, "합계")}</td>
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
          {detailRow(TOTAL, totalLineups)}
        </tbody>
      </table>
    </div>
  );
}
