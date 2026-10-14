import { useEffect, useMemo, useRef, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { getIncDay, saveIncAccounts } from "@/api/incentive";
import type { IncDayView } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import IncentiveDetailModal from "./IncentiveDetailModal";
import { STATUS, adjText, amt, shift, wd } from "./util";
import IncentiveOwnerModal from "./IncentiveOwnerModal";
import type { ChipTone } from "@/components/ui/Chip";
const OWNER_SRC: Record<string, [string, ChipTone]> = { chosen: ["지정", "internal"], log: ["근무 기록", "neutral"], fixed: ["고정", "neutral"] };


type Props = { date: string; onDate: (d: string) => void; isAdmin: boolean; onDirty?: (n: number) => void };
const str = (v: number | null) => (v == null ? "" : String(v));

export default function IncentiveDayTab({ date, onDate, isAdmin, onDirty }: Props) {
  const [view, setView] = useState<IncDayView | null>(null);
  const [forms, setForms] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [ownerId, setOwnerId] = useState<number | null>(null);
  const refs = useRef<Record<number, HTMLInputElement | null>>({});
  const base = useRef<Record<number, string>>({});

  /** keep=true: 상세 창 저장 후 다시 불러올 때 입력 중인 고객사 수는 유지 */
  async function load(d: string, keep = false) {
    if (!keep) setLoading(true);
    try {
      const v = await getIncDay(d);
      const nb: Record<number, string> = Object.fromEntries(v.items.map((it) => [it.manager_id, str(it.accounts)]));
      setForms((prev) => Object.fromEntries(v.items.map((it) => {
        const k = it.manager_id;
        const p = prev[k];
        return [k, keep && p !== undefined && p !== base.current[k] ? p : nb[k]];
      })));
      base.current = nb;
      setView(v);
      setError("");
    } catch (e) {
      if (!keep) setView(null);
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { setNote(""); setOpenId(null); setOwnerId(null); load(date); }, [date]);

  const rows = useMemo(() => (view?.items ?? []).map((it) => {
    const f = forms[it.manager_id] ?? str(it.accounts);
    return { it, f, dirty: f !== str(it.accounts), bad: f !== "" && !/^\d{1,3}$/.test(f) };
  }), [view, forms]);
  const dirty = rows.filter((r) => r.dirty);
  const bad = dirty.filter((r) => r.bad);
  const warned = rows.filter((r) => r.it.warns.length > 0);
  const locked = !isAdmin || !view || view.closed || view.future;
  const ownerLocked = !isAdmin || !view || view.closed;
  useEffect(() => { onDirty?.(dirty.length); }, [dirty.length]);

  function go(d: string) {
    if (d === date) return;
    if (dirty.length > 0 && !confirm(`저장하지 않은 고객사 수 ${dirty.length}건이 있습니다. 취소하고 이동할까요?`)) return;
    onDate(d);
  }
  function next(i: number) {
    for (let k = i + 1; k < rows.length; k++) {
      const el = refs.current[rows[k].it.manager_id];
      if (el && !el.disabled) { el.focus(); el.select(); return; }
    }
  }

  async function save() {
    if (!view || dirty.length === 0 || bad.length > 0) return;
    const cleared = dirty.filter((r) => r.f === "");
    if (cleared.length && !confirm(
      `고객사 수를 지우는 계정 ${cleared.length}곳: ${cleared.map((r) => r.it.manager_name).join(", ")}\n` +
      "지우면 그날 인센티브가 '고객사 수 입력 필요'로 바뀝니다. 계속할까요?")) return;
    setBusy(true);
    try {
      const r = await saveIncAccounts(view.date, dirty.map(({ it, f }) => ({
        manager_id: it.manager_id, value: f === "" ? null : Number(f) })));
      await load(view.date);
      setNote(`✓ 고객사 수 저장 ${r.saved}건${r.cleared ? ` · 지움 ${r.cleared}건` : ""}` +
        `${r.unchanged ? ` · 기존과 같아 건너뜀 ${r.unchanged}건` : ""}`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const sum = (k: "stops" | "gajung_qty" | "mil_qty" | "product_total" | "extras" | "total") =>
    rows.reduce((a, r) => a + (r.it[k] ?? 0), 0);
  const openRow = view?.items.find((x) => x.manager_id === openId) ?? null;

  return (
    <Panel
      title={`${date} (${wd(date)}) 인센티브 · 계정 ${num(rows.length)}곳`}
      right={
        <>
          {view?.closed && <Chip tone="warn">마감된 달 · 수정 불가</Chip>}
          {view?.future && <Chip tone="caution">미래 날짜 · 입력 불가</Chip>}
          <Button size="sm" onClick={() => go(shift(date, -1))} aria-label="전날">◀</Button>
          <input type="date" className="input input-sm" value={date} onChange={(e) => e.target.value && go(e.target.value)} />
          <Button size="sm" onClick={() => go(shift(date, 1))} aria-label="다음날">▶</Button>
          <Button size="sm" onClick={() => go(todayKst())}>오늘</Button>
          {isAdmin && (
            <Button size="sm" variant="primary" onClick={save}
              disabled={locked || busy || dirty.length === 0 || bad.length > 0}>
              {busy ? "저장 중…" : `고객사 수 ${num(dirty.length)}건 저장`}
            </Button>
          )}
        </>
      }
      desc={<>
        제품 수 = 중식 가정식 + 중식 밀(프레시·라이트)을 자동으로 셉니다. 석식·파일럿 가정식은 참고용으로만 보여주고 집계하지 않습니다.
        고객사 수(수거 포함)만 입력하고 Enter로 다음 계정으로 넘어가세요. 입력하기 전에는 인센티브가 확정되지 않습니다.
        퀵 발송·다른 매니저 처리 같은 배송지 제외, 제품 수 조정(목록), 미지급, 특수 수당은 [상세]에서 처리합니다.
      </>}
    >
      {error && <ErrorBox message={error} />}
      {note && <div className="notice mt">{note}</div>}
      {bad.length > 0 && (
        <div className="wl-block">고객사 수는 0~999 숫자로 입력하세요: {bad.map((r) => r.it.manager_name).join(", ")}</div>
      )}
      {warned.length > 0 && (
        <div className="notice mt">
          {warned.map((r) => <div key={r.it.manager_id} className="wl-warn">⚠ {r.it.manager_name}: {r.it.warns.join(" / ")}</div>)}
        </div>
      )}
      {view && (
        <div className="muted small mt">
          지급 예정 합계 {num(view.totals.total)}원 (데일리 인센티브 {num(view.totals.payable)} + 특수 수당 {num(view.totals.extras)})
          {view.totals.need_accounts > 0 && ` · 고객사 수 입력 필요 ${view.totals.need_accounts}곳`}
          {view.totals.held > 0 && ` · 미지급 ${view.totals.held}곳`}
        </div>
      )}
      {loading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <div className="muted small">이 날짜에 배정된 배송이 없습니다.</div>
      ) : (
        <DataTable columns={["계정", "담당", { label: "배송지", num: true }, { label: "가정식", num: true },
          { label: "밀", num: true }, { label: "석식·파일럿(참고)", num: true }, { label: "제외·조정", num: true },
          { label: "제품 수", num: true }, "고객사 수", { label: "제품 인센", num: true },
          { label: "고객사 인센", num: true }, { label: "데일리", num: true }, { label: "특수 수당", num: true },
          { label: "합계", num: true }, "상태", ""]}>
          {rows.map(({ it, f, dirty: d, bad: b }, i) => (
            <tr key={it.manager_id} className={it.stops === 0 ? "off" : undefined}>
              <td><span className="inc-swatch" style={{ background: it.color ?? "#94a3b8" }} />{it.manager_name}</td>
              <td>
                {it.owner.worker_id != null ? (
                  <>{it.owner.name} <Chip tone={OWNER_SRC[it.owner.source ?? "fixed"][1]} title={it.owner.memo ?? ""}>
                    {OWNER_SRC[it.owner.source ?? "fixed"][0]}</Chip></>
                ) : it.stops > 0 || it.extras > 0 ? <Chip tone="warn" title={it.owner.why ?? ""}>미확인</Chip> : "-"}
                {!ownerLocked && <Button size="sm" onClick={() => setOwnerId(it.manager_id)}>변경</Button>}
              </td>              
              <td className="num">{num(it.stops)}</td>
              <td className="num">{num(it.gajung_qty)}</td>
              <td className="num">{num(it.mil_qty)}</td>
              <td className="num inc-ref" title="석식 · 파일럿 가정식 (집계 제외)">
                {it.dinner_qty || it.pilot_qty ? `${num(it.dinner_qty)} · ${num(it.pilot_qty)}` : "-"}
              </td>
              <td className="num">{adjText(it)}</td>
              <td className="num"><b>{num(it.product_total)}</b></td>
              <td>
                {it.stops > 0 ? (
                  <>
                    <input className={`input input-sm inc-acc${b ? " bad" : d ? " dirty" : ""}`} inputMode="numeric"
                      value={f} placeholder="입력" disabled={locked}
                      ref={(el) => { refs.current[it.manager_id] = el; }}
                      onChange={(e) => setForms((s) => ({ ...s, [it.manager_id]: e.target.value.trim() }))}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); next(i); } }} />
                    <div className="inc-ref">주문 고객사 {num(it.order_accounts)}</div>
                  </>
                ) : <span className="muted small">배송 없음</span>}
              </td>
              <td className="num">{amt(it.product_incentive)}</td>
              <td className="num">{amt(it.account_incentive)}</td>
              <td className="num">
                {it.held ? <span className="inc-held"><s>{amt(it.incentive)}</s> 0</span> : amt(it.payable)}
              </td>
              <td className="num">{it.extras ? num(it.extras) : "-"}</td>
              <td className="num"><b>{num(it.total)}</b></td>
              <td>
                <Chip tone={STATUS[it.status][1]}>{STATUS[it.status][0]}</Chip>
                {d && <Chip tone="neutral">저장 전</Chip>}
                {it.warns.length > 0 && <span className="inc-warn" title={it.warns.join("\n")}>⚠{it.warns.length}</span>}
              </td>
              <td><Button size="sm" onClick={() => setOpenId(it.manager_id)}>상세</Button></td>
            </tr>
          ))}
          <tr className="inc-total">
            <td>합계</td><td />
            <td className="num">{num(sum("stops"))}</td>
            <td className="num">{num(sum("gajung_qty"))}</td>
            <td className="num">{num(sum("mil_qty"))}</td>
            <td /><td />
            <td className="num">{num(sum("product_total"))}</td>
            <td /><td /><td />
            <td className="num">{num(view?.totals.payable)}</td>
            <td className="num">{num(sum("extras"))}</td>
            <td className="num">{num(sum("total"))}</td>
            <td /><td />
          </tr>
        </DataTable>
      )}
      {openRow && view && (
        <IncentiveDetailModal row={openRow} view={view} locked={locked}
          onClose={() => setOpenId(null)} onChanged={() => load(view.date, true)} />
      )}
      {ownerId != null && view && view.items.find((x) => x.manager_id === ownerId) && (
        <IncentiveOwnerModal row={view.items.find((x) => x.manager_id === ownerId)!} view={view}
          onClose={() => setOwnerId(null)} onSaved={() => load(view.date, true)} />
      )}      
    </Panel>
  );
}
