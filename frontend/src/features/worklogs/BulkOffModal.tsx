import { useMemo, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import { INCOME_LABEL } from "@/api/workers";
import { OFF_LABEL, OFF_REASONS, isWorkday, saveWorkOffsMulti, spanOn, termOut } from "@/api/worklogs";
import type { OffReason, WorkMonthPerson } from "@/api/worklogs";
import { errText } from "@/lib/form";
import { num } from "@/lib/format";

const WD = "일월화수목금토";
type Mode = "set" | "clear";

type Props = {
  month: string; lastDay: number; day: number; people: WorkMonthPerson[]; closed: boolean;
  onClose: () => void; onSaved: (msg: string) => void;
};

/** [S2-P4d-3] 월 표 → 여러 날짜 × 여러 명 휴무 지정·해제 (공휴일·연휴·공장 휴무 등) */
export default function BulkOffModal({ month, lastDay, day: firstDay, people, closed, onClose, onSaved }: Props) {
  const [days, setDays] = useState<Set<number>>(() => new Set([firstDay]));
  const [mode, setMode] = useState<Mode>("set");
  const [workOnly, setWorkOnly] = useState(true);
  const [reason, setReason] = useState<OffReason>("holiday");
  const [memo, setMemo] = useState("");
  const [picked, setPicked] = useState<Set<number> | null>(null);   // null = 기본 선택
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mm = Number(month.slice(5));
  const isoOf = (d: number) => `${month}-${String(d).padStart(2, "0")}`;
  const wdOf = (d: number) => new Date(`${isoOf(d)}T00:00:00Z`).getUTCDay();
  const picks = useMemo(() => [...days].sort((a, b) => a - b), [days]);

  // 사람 × 선택 날짜: why = 이 쌍을 적용하지 않는 사유 (null = 적용)
  const rows = useMemo(() => people.map((p) => {
    const cells = picks.map((d) => {
      const iso = `${month}-${String(d).padStart(2, "0")}`;
      const c = spanOn(p.contracts, iso)?.contract ?? null;
      const log = p.days[String(d)] ?? null;
      const off = p.offs[String(d)] ?? null;
      const out = termOut(p.start_date, p.end_date, iso);
      const work = isWorkday(c, iso);
      const why = mode === "clear" ? (off ? null : "휴무 아님")
        : out ?? (log ? "근무 기록 있음" : !c ? "계약 없음" : workOnly && !work ? "쉬는 요일" : null);
      return { d, iso, c, log, off, out, work, why };
    });
    const ok = cells.filter((x) => !x.why);
    return { p, cells, ok, fresh: ok.filter((x) => !x.off) };
  }).filter((r) => r.cells.some((x) => !x.out || x.off)), [people, picks, mode, workOnly, month]);

  // 기본 선택: 지정 = 휴무 없는 적용일이 하루라도 있는 사람 / 해제 = 선택 날짜에 휴무가 있는 사람
  const defaults = useMemo(() => new Set(rows
    .filter((r) => (mode === "clear" ? r.ok.length : r.fresh.length) > 0)
    .map((r) => r.p.worker_id)), [rows, mode]);
  const sel = picked ?? defaults;
  const selectable = rows.filter((r) => r.ok.length > 0);
  const chosen = selectable.filter((r) => sel.has(r.p.worker_id));
  const pairs = chosen.flatMap((r) => r.ok.map((x) => ({ work_date: x.iso, worker_id: r.p.worker_id })));

  function reset(fn: () => void) { fn(); setPicked(null); setError(""); }
  function toggle(id: number) {
    const s = new Set(sel);
    if (s.has(id)) s.delete(id); else s.add(id);
    setPicked(s);
  }
  function toggleDay(d: number) {
    reset(() => setDays((s) => { const n = new Set(s); if (n.has(d)) n.delete(d); else n.add(d); return n; }));
  }

  const dayLabel = picks.length <= 5
    ? picks.map((d) => `${mm}/${d}`).join(", ")
    : `${picks.slice(0, 5).map((d) => `${mm}/${d}`).join(", ")} 외 ${picks.length - 5}일`;

  async function save() {
    if (pairs.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const r = await saveWorkOffsMulti(pairs, mode === "set" ? reason : null, mode === "set" ? memo.trim() || null : null);
      const parts = [mode === "set" ? `휴무 지정 ${num(r.saved)}건` : `휴무 해제 ${num(r.released)}건`];
      if (r.unchanged) parts.push(`기존과 같아 건너뜀 ${num(r.unchanged)}건`);
      if (r.skipped.length) parts.push(`제외: ${r.skipped.join(", ")}`);
      onSaved(`${dayLabel}: ${parts.join(" · ")}`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  function status(r: (typeof rows)[number]) {
    if (picks.length === 1) {
      const x = r.cells[0];
      return x.log ? <Chip tone="ok">근무 기록 있음</Chip>
        : x.off ? <Chip>휴무 · {OFF_LABEL[x.off.reason]}{x.off.memo ? ` · ${x.off.memo}` : ""}</Chip>
        : x.out ? <span className="muted small">{x.out}</span>
        : !x.c ? <Chip tone="danger">계약 없음</Chip>
        : <span className="muted small">{x.work ? "근무 요일" : "쉬는 요일"}</span>;
    }
    const why: Record<string, number> = {};
    for (const x of r.cells) if (x.why) why[x.why] = (why[x.why] ?? 0) + 1;
    const offs = r.ok.length - r.fresh.length;
    return (
      <span className="small">
        적용 <b>{r.ok.length}</b>일
        {mode === "set" && offs > 0 && <span className="muted"> (이미 휴무 {offs}일 → 사유 변경)</span>}
        {Object.keys(why).length > 0 && (
          <span className="muted"> · 제외 {Object.entries(why).map(([k, n]) => `${k} ${n}`).join(" · ")}</span>
        )}
      </span>
    );
  }

  const blanks = wdOf(1);
  return (
    <Modal open size="lg" onClose={onClose}
      title={<>휴무 일괄 {mode === "set" ? "지정" : "해제"} · {picks.length === 1
        ? `${mm}월 ${picks[0]}일 (${WD[wdOf(picks[0])]})` : `${mm}월 ${picks.length}일 선택`}</>}
      footer={<>
        <span className="muted small grow">선택 {num(chosen.length)}명 · 날짜 {num(picks.length)}일 · 적용 {num(pairs.length)}건</span>
        <Button onClick={onClose}>닫기</Button>
        <Button variant="primary" onClick={save} disabled={closed || busy || pairs.length === 0}>
          {busy ? "저장 중…" : `${num(pairs.length)}건 휴무 ${mode === "set" ? "지정" : "해제"}`}
        </Button>
      </>}
    >
      {error && <ErrorBox message={error} />}
      {closed && <Chip tone="warn">마감된 달 · 수정 불가</Chip>}
      <div className="bo-cal" role="group" aria-label="날짜 선택">
        {Array.from(WD).map((w) => <span key={w} className="bo-cal-h">{w}</span>)}
        {Array.from({ length: blanks }, (_, i) => <span key={`b${i}`} />)}
        {Array.from({ length: lastDay }, (_, i) => i + 1).map((d) => {
          const w = wdOf(d);
          const cls = ["bo-day", days.has(d) ? "on" : "", w === 0 ? "sun" : w === 6 ? "sat" : ""].filter(Boolean).join(" ");
          return (
            <button key={d} type="button" className={cls} disabled={closed} aria-pressed={days.has(d)}
              onClick={() => toggleDay(d)}>{d}</button>
          );
        })}
      </div>
      <div className="bo-tools">
        <span className="muted small">날짜를 눌러 여러 날을 고릅니다{picks.length === 0 ? " — 하루 이상 고르세요" : ""}.</span>
        {picks.length > 1 && <Button size="sm" variant="ghost" onClick={() => reset(() => setDays(new Set()))}>날짜 모두 끄기</Button>}
      </div>
      <div className="bo-tools">
        <div className="seg bo-seg">
          <button type="button" className={mode === "set" ? "on" : undefined} onClick={() => reset(() => setMode("set"))}>지정</button>
          <button type="button" className={mode === "clear" ? "on" : undefined} onClick={() => reset(() => setMode("clear"))}>해제</button>
        </div>
        {mode === "set" && <>
          <select className="input input-sm" value={reason} onChange={(e) => setReason(e.target.value as OffReason)}>
            {OFF_REASONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input className="input input-sm bo-memo" value={memo} maxLength={200} placeholder="메모 (예: 추석)"
            onChange={(e) => setMemo(e.target.value)} />
          <label className="muted small" title="끄면 계약상 쉬는 요일에도 휴무를 넣습니다">
            <input type="checkbox" checked={workOnly} onChange={(e) => reset(() => setWorkOnly(e.target.checked))} /> 근무 요일만
          </label>
        </>}
      </div>
      <div className="bo-tools">
        <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(selectable.map((r) => r.p.worker_id)))}>전체 선택</Button>
        <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>전체 해제</Button>
        <span className="muted small">
          {mode === "set"
            ? "고른 사람마다 선택 날짜 중 적용 가능한 날에만 넣습니다 (근무 기록·입사 전·퇴사 뒤·계약 없음·쉬는 요일은 자동 제외). 이미 휴무인 날은 사유가 바뀝니다."
            : "기본 선택 = 선택 날짜에 휴무가 지정된 사람 전체."}
        </span>
      </div>
      <div className="bo-wrap">
        <table className="tbl bo-tbl">
          <thead><tr><th className="bo-chk" /><th>이름</th><th>{picks.length === 1 ? "그날 상태" : "선택 날짜 적용"}</th></tr></thead>
          <tbody>
            {rows.map((r) => {
              const dis = r.ok.length === 0;
              return (
                <tr key={r.p.worker_id} className={dis ? "off" : undefined}>
                  <td className="bo-chk">
                    <input type="checkbox" checked={!dis && sel.has(r.p.worker_id)} disabled={dis || closed}
                      onChange={() => toggle(r.p.worker_id)} aria-label={`${r.p.name} 선택`} />
                  </td>
                  <td><b>{r.p.name}</b> <span className="muted small">{INCOME_LABEL[r.p.income_type]}</span></td>
                  <td>{status(r)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}
