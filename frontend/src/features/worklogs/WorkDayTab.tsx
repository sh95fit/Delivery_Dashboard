import { useEffect, useMemo, useRef, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { nowHms } from "@/components/ui/SaveNote";
import type { ManagerRow } from "@/api/masters";
import { INCOME_LABEL } from "@/api/workers";
import { deleteWorkLog, getWorkDay, hmm, saveWorkDay } from "@/api/worklogs";
import type { WorkDayItem, WorkDayView, WorkLogInput } from "@/api/worklogs";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import { EMPTY_FORM, contractText, defaultBreak, defaultIn, isDefaultBreak, isDefaultIn, logToForm, preview, sameForm, toInput } from "./calc";
import type { LogForm } from "./calc";

const WD = "일월화수목금토";
const wd = (d: string) => WD[new Date(`${d}T00:00:00Z`).getUTCDay()];
function shift(d: string, n: number) {
  const t = new Date(`${d}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}
const initOf = (it: WorkDayItem) => logToForm(it.log, it.contract);

type Props = { date: string; onDate: (d: string) => void; managers: ManagerRow[]; isAdmin: boolean; reloadKey?: number };
type Result = { at: string; saved: number; unchanged: number; warns: Record<string, string[]> };

export default function WorkDayTab({ date, onDate, managers, isAdmin, reloadKey = 0 }: Props) {
  const [view, setView] = useState<WorkDayView | null>(null);
  const [forms, setForms] = useState<Record<number, LogForm>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const outRefs = useRef<Record<number, HTMLInputElement | null>>({});

  async function load(d: string) {
    setLoading(true);
    try {
      const v = await getWorkDay(d);
      setView(v);
      setForms(Object.fromEntries(v.items.map((it) => [it.worker_id, initOf(it)])));
      setError("");
    } catch (e) {
      setView(null);
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { setResult(null); load(date); }, [date]);

  const rows = useMemo(() => (view?.items ?? []).map((it) => {
    const init = initOf(it);
    const f = forms[it.worker_id] ?? init;
    const dirty = !sameForm(f, init);
    return { it, f, dirty, pv: preview(it.contract, f), cleared: dirty && !!it.log && f.out === "" };
  }), [view, forms]);

  const toSave = rows.filter((r) => r.dirty && r.f.out !== "");
  const blocked = toSave.filter((r) => r.pv.err || !r.it.contract);
  const dirtyCount = rows.filter((r) => r.dirty).length;
  // 월 표 팝업에서 저장하면 다시 불러옴 (입력 중인 값이 있으면 덮어쓰지 않음)
  useEffect(() => { if (reloadKey && dirtyCount === 0) load(date); }, [reloadKey]);
  const locked = !isAdmin || !view || view.closed || view.future;
  const sortedManagers = useMemo(
    () => managers.filter((m) => m.name).sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true })),
    [managers],
  );

  function set(wid: number, patch: Partial<LogForm>) {
    setForms((s) => ({ ...s, [wid]: { ...(s[wid] ?? EMPTY_FORM), ...patch } }));
  }
  function go(d: string) {
    if (d === date) return;
    if (dirtyCount > 0 && !confirm(`저장하지 않은 변경 ${dirtyCount}건이 있습니다. 버리고 이동할까요?`)) return;
    onDate(d);
  }
  function next(i: number) {
    for (let k = i + 1; k < rows.length; k++) {
      const el = outRefs.current[rows[k].it.worker_id];
      if (el && !el.disabled) { el.focus(); return; }
    }
  }

  async function save() {
    if (!view || toSave.length === 0) return;
    setBusy(true);
    try {
      const body: WorkLogInput[] = toSave.map(({ it, f }) => ({ worker_id: it.worker_id, ...toInput(it.contract, f) }));
      const r = await saveWorkDay(view.date, body);
      await load(view.date);
      setResult({ at: nowHms(), saved: r.saved, unchanged: r.unchanged, warns: r.warns });
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(it: WorkDayItem) {
    if (!view || !it.log) return;
    if (!confirm(`${it.name}님의 ${view.date} 기록을 삭제할까요? (비근무 처리, 변경 기록은 남음)`)) return;
    setBusy(true);
    try {
      await deleteWorkLog(it.log.id);
      await load(view.date);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const worked = rows.filter((r) => r.it.log).length;

  return (
    <Panel
      title={`${date} (${wd(date)}) · 근무 ${num(worked)}명 / 대상 ${num(rows.length)}명`}
      right={
        <>
          {view?.closed && <Chip tone="warn">마감된 달 · 수정 불가</Chip>}
          {view?.future && <Chip tone="caution">미래 날짜</Chip>}
          <Button size="sm" onClick={() => go(shift(date, -1))} aria-label="전날">◀</Button>
          <input type="date" className="input input-sm" value={date} onChange={(e) => e.target.value && go(e.target.value)} />
          <Button size="sm" onClick={() => go(shift(date, 1))} aria-label="다음날">▶</Button>
          <Button size="sm" onClick={() => go(todayKst())}>오늘</Button>
          {isAdmin && (
            <Button size="sm" variant="primary" onClick={save}
              disabled={locked || busy || toSave.length === 0 || blocked.length > 0}>
              {busy ? "저장 중…" : `변경 ${num(toSave.length)}건 저장`}
            </Button>
          )}
        </>
      }
      desc={<>
        출근·휴게는 계약 기본값이 <span className="wl-def-sample">회색</span>으로 채워져 있습니다.
        퇴근(지문)만 입력하고, 지문 출근이 지정보다 늦은 날이나 휴게가 다른 날만 고치세요 (고친 값은 검정).
        지문이 지정보다 빠르면 지정 시각으로 인정. 휴게 = 유급시간에서 빼는 분. 기록이 없는 날은 비근무입니다.
      </>}
    >
      {error && <ErrorBox message={error} />}
      {result && (
        <div className="notice mt">
          ✓ {result.at} 저장 {num(result.saved)}건{result.unchanged ? ` · 변경 없음 ${num(result.unchanged)}건` : ""}
          {Object.entries(result.warns).map(([n, ws]) => <div key={n} className="wl-warn">⚠ {n}: {ws.join(", ")}</div>)}
        </div>
      )}
      {blocked.length > 0 && (
        <div className="wl-block">
          저장 불가 {blocked.length}건: {blocked.map((r) => `${r.it.name}(${r.pv.err || "계약 없음"})`).join(", ")}
        </div>
      )}
      {loading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <div className="muted small">이 날짜에 근무 대상(활성 시급 계약)이 없습니다.</div>
      ) : (
        <DataTable columns={["이름", "지정", "출근(지문)", "퇴근(지문)", "휴게(분)", "그날 계정", "메모",
          { label: "유급", num: true }, "상태", ""]}>
          {rows.map(({ it, f, dirty, pv, cleared }, i) => {
            const c = it.contract;
            const dis = locked || !c;
            const cls = [it.active ? "" : "off", dirty ? "wl-dirty" : ""].filter(Boolean).join(" ");
            return (
              <tr key={it.worker_id} className={cls || undefined}>
                <td>{it.name} <span className="muted small">{INCOME_LABEL[it.income_type]}</span></td>
                <td className="small">{c ? contractText(c) : <Chip tone="danger">계약 없음</Chip>}</td>
                <td>
                  <input type="time" className={`input input-sm wl-time${isDefaultIn(c, f.punch) ? " wl-def" : ""}`}
                    value={f.punch} disabled={dis}
                    onChange={(e) => set(it.worker_id, { punch: e.target.value })}
                    onBlur={() => { if (!f.punch) set(it.worker_id, { punch: defaultIn(c) }); }} />
                  {pv.cin != null && toMinSafe(f.punch) !== pv.cin && <div className="muted small">인정 {hmm(pv.cin)}</div>}
                </td>
                <td>
                  <input type="time" className="input input-sm wl-time" value={f.out} disabled={dis}
                    ref={(el) => { outRefs.current[it.worker_id] = el; }}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); next(i); } }}
                    onChange={(e) => set(it.worker_id, { out: e.target.value })} />
                </td>
                <td>
                  <input type="number" min={0} max={600} className={`input input-sm wl-num${isDefaultBreak(c, f.brk) ? " wl-def" : ""}`}
                    value={f.brk} disabled={dis}
                    onChange={(e) => set(it.worker_id, { brk: e.target.value })}
                    onBlur={() => { if (f.brk === "" && c) set(it.worker_id, { brk: String(defaultBreak(c)) }); }} />
                </td>
                <td>
                  <select className="input input-sm wl-sel" value={f.mid} disabled={dis}
                    onChange={(e) => set(it.worker_id, { mid: e.target.value })}>
                    <option value="">고정: {it.fixed_manager_name ?? "없음"}</option>
                    {sortedManagers.map((m) => <option key={m.manager_id} value={m.manager_id}>{m.name}</option>)}
                  </select>
                </td>
                <td>
                  <input className="input input-sm wl-memo" value={f.memo} maxLength={200} disabled={dis}
                    onChange={(e) => set(it.worker_id, { memo: e.target.value })} />
                </td>
                <td className="num">
                  {pv.err ? <Chip tone="danger">{pv.err}</Chip> : f.out ? hmm(pv.paid) : ""}
                  {!dirty && it.log?.ot_min ? <div className="muted small">계약 외 {hmm(it.log.ot_min)}</div> : null}
                </td>
                <td>
                  {cleared ? <Chip tone="caution">퇴근 비움 · 삭제 버튼 사용</Chip>
                    : dirty ? <Chip tone="caution">변경</Chip>
                    : it.log ? <Chip tone="ok">저장됨</Chip>
                    : <span className="muted small">미입력</span>}
                </td>
                <td>{it.log && !locked && <Button size="sm" variant="ghost" disabled={busy} onClick={() => remove(it)}>삭제</Button>}</td>
              </tr>
            );
          })}
        </DataTable>
      )}
    </Panel>
  );
}

/** "06:41" → 401 (인정 출근 안내 표시 여부 판단용) */
function toMinSafe(v: string): number | null {
  const m = /^(\d{1,2}):(\d{2})/.exec(v);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}
