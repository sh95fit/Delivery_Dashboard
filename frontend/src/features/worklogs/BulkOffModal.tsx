import { useMemo, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import { INCOME_LABEL } from "@/api/workers";
import { OFF_LABEL, OFF_REASONS, isWorkday, saveWorkOffs, spanOn } from "@/api/worklogs";
import type { OffReason, WorkMonthPerson } from "@/api/worklogs";
import { errText } from "@/lib/form";
import { num } from "@/lib/format";

const WD = "일월화수목금토";
type Mode = "set" | "clear";

type Props = {
  month: string; lastDay: number; day: number; people: WorkMonthPerson[]; closed: boolean;
  onClose: () => void; onSaved: (msg: string) => void;
};

/** 월 표 날짜 머리글 → 그날 여러 명 휴무 지정·해제 (공휴일·공장 휴무 등) */
export default function BulkOffModal({ month, lastDay, day: firstDay, people, closed, onClose, onSaved }: Props) {
  const [day, setDay] = useState(firstDay);
  const [mode, setMode] = useState<Mode>("set");
  const [reason, setReason] = useState<OffReason>("holiday");
  const [memo, setMemo] = useState("");
  const [picked, setPicked] = useState<Set<number> | null>(null);   // null = 기본 선택
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isoOf = (d: number) => `${month}-${String(d).padStart(2, "0")}`;
  const wdOf = (d: number) => new Date(`${isoOf(d)}T00:00:00Z`).getUTCDay();
  const iso = isoOf(day);

  const rows = useMemo(() => people
    .filter((p) => p.active || p.offs[String(day)])
    .map((p) => {
      const c = spanOn(p.contracts, iso)?.contract ?? null;
      const log = p.days[String(day)] ?? null;
      const off = p.offs[String(day)] ?? null;
      const why = mode === "set" ? (log ? "근무 기록 있음" : !c ? "계약 없음" : null) : (!off ? "휴무 아님" : null);
      return { p, c, log, off, work: isWorkday(c, iso), why };
    }), [people, day, iso, mode]);

  // 기본 선택: 지정 = 그날 근무 요일이고 휴무 없는 사람 / 해제 = 휴무 지정된 사람 전체
  const defaults = useMemo(() => new Set(rows
    .filter((r) => !r.why && (mode === "clear" || (r.work && !r.off)))
    .map((r) => r.p.worker_id)), [rows, mode]);
  const sel = picked ?? defaults;
  const selectable = rows.filter((r) => !r.why);
  const chosen = selectable.filter((r) => sel.has(r.p.worker_id));

  function reset(fn: () => void) { fn(); setPicked(null); setError(""); }
  function toggle(id: number) {
    const s = new Set(sel);
    if (s.has(id)) s.delete(id); else s.add(id);
    setPicked(s);
  }

  async function save() {
    if (chosen.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const r = await saveWorkOffs(iso, chosen.map((x) => x.p.worker_id),
        mode === "set" ? reason : null, mode === "set" ? memo.trim() || null : null);
      const parts = [mode === "set" ? `휴무 지정 ${num(r.saved)}명` : `휴무 해제 ${num(r.released)}명`];
      if (r.unchanged) parts.push(`기존과 같아 건너뜀 ${num(r.unchanged)}명`);
      if (r.skipped.length) parts.push(`근무 기록이 있어 제외: ${r.skipped.join(", ")}`);
      onSaved(`${Number(month.slice(5))}/${day}: ${parts.join(" · ")}`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open size="lg" onClose={onClose}
      title={<>휴무 일괄 {mode === "set" ? "지정" : "해제"} · {Number(month.slice(5))}월 {day}일 ({WD[wdOf(day)]})</>}
      footer={<>
        <span className="muted small grow">선택 {num(chosen.length)}명 / 가능 {num(selectable.length)}명</span>
        <Button onClick={onClose}>닫기</Button>
        <Button variant="primary" onClick={save} disabled={closed || busy || chosen.length === 0}>
          {busy ? "저장 중…" : `${num(chosen.length)}명 휴무 ${mode === "set" ? "지정" : "해제"}`}
        </Button>
      </>}
    >
      {error && <ErrorBox message={error} />}
      {closed && <Chip tone="warn">마감된 달 · 수정 불가</Chip>}
      <div className="bo-tools">
        <select className="input input-sm" value={day} onChange={(e) => reset(() => setDay(Number(e.target.value)))}>
          {Array.from({ length: lastDay }, (_, i) => i + 1).map((d) => (
            <option key={d} value={d}>{d}일 ({WD[wdOf(d)]})</option>
          ))}
        </select>
        <div className="seg bo-seg">
          <button type="button" className={mode === "set" ? "on" : undefined} onClick={() => reset(() => setMode("set"))}>지정</button>
          <button type="button" className={mode === "clear" ? "on" : undefined} onClick={() => reset(() => setMode("clear"))}>해제</button>
        </div>
        {mode === "set" && <>
          <select className="input input-sm" value={reason} onChange={(e) => setReason(e.target.value as OffReason)}>
            {OFF_REASONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input className="input input-sm bo-memo" value={memo} maxLength={200} placeholder="메모 (예: 한글날)"
            onChange={(e) => setMemo(e.target.value)} />
        </>}
      </div>
      <div className="bo-tools">
        <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(selectable.map((r) => r.p.worker_id)))}>전체 선택</Button>
        <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>전체 해제</Button>
        <span className="muted small">
          {mode === "set"
            ? "기본 선택 = 그날이 근무 요일이고 휴무가 없는 사람. 이미 휴무인 사람을 고르면 사유가 바뀝니다. 근무 기록이 있는 사람은 고를 수 없습니다."
            : "기본 선택 = 그날 휴무가 지정된 사람 전체."}
        </span>
      </div>
      <div className="bo-wrap">
        <table className="tbl bo-tbl">
          <thead><tr><th className="bo-chk" /><th>이름</th><th>그날 상태</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.p.worker_id} className={r.why ? "off" : undefined}>
                <td className="bo-chk">
                  <input type="checkbox" checked={!r.why && sel.has(r.p.worker_id)} disabled={!!r.why || closed}
                    onChange={() => toggle(r.p.worker_id)} aria-label={`${r.p.name} 선택`} />
                </td>
                <td><b>{r.p.name}</b> <span className="muted small">{INCOME_LABEL[r.p.income_type]}</span></td>
                <td>
                  {r.log ? <Chip tone="ok">근무 기록 있음</Chip>
                    : r.off ? <Chip>휴무 · {OFF_LABEL[r.off.reason]}{r.off.memo ? ` · ${r.off.memo}` : ""}</Chip>
                    : !r.c ? <Chip tone="danger">계약 없음</Chip>
                    : <span className="muted small">{r.work ? "근무 요일" : "쉬는 요일"}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}
