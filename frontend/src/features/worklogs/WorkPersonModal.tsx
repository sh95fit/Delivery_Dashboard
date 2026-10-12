import { useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import type { ManagerRow } from "@/api/masters";
import { INCOME_LABEL } from "@/api/workers";
import { OFF_LABEL, OFF_REASONS, hmm, isWorkday, saveWorkPerson, spanOn, toMin } from "@/api/worklogs";
import type { OffReason, WorkLogDateInput, WorkMonthPerson, WorkOffInput } from "@/api/worklogs";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import { EMPTY_FORM, contractText, defaultBreak, defaultIn, isDefaultBreak, isDefaultIn, logToForm, preview, sameForm, toInput } from "./calc";
import type { LogForm } from "./calc";

const WD = "일월화수목금토";
const isoOf = (month: string, d: number) => `${month}-${String(d).padStart(2, "0")}`;

type Props = {
  person: WorkMonthPerson; month: string; lastDay: number; focusDay: number | null;
  closed: boolean; isAdmin: boolean; managers: ManagerRow[];
  onClose: () => void; onSaved: (msg: string) => void;
};

/** 월 표에서 한 사람의 한 달 근무·휴무 입력 (이름 클릭 = 전체, 날짜 칸 클릭 = 그날로 이동) */
export default function WorkPersonModal({ person, month, lastDay, focusDay, closed, isAdmin, managers, onClose, onSaved }: Props) {
  const today = todayKst();
  const [y, m] = month.split("-").map(Number);
  const contractOn = (d: number) => spanOn(person.contracts, isoOf(month, d))?.contract ?? null;
  const init = useMemo(() => {
    const o: Record<number, LogForm> = {};
    for (let d = 1; d <= lastDay; d++) {
      o[d] = logToForm(person.days[String(d)] ?? null, contractOn(d), person.offs[String(d)] ?? null);
    }
    return o;
  }, [person, lastDay, month]);
  const [forms, setForms] = useState<Record<number, LogForm>>(init);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const outRefs = useRef<Record<number, HTMLInputElement | null>>({});
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({});
  const missing = useMemo(() => new Set(person.missing_days), [person]);

  useEffect(() => { setForms(init); }, [init]);

  const rows = useMemo(() => Array.from({ length: lastDay }, (_, i) => {
    const d = i + 1;
    const iso = isoOf(month, d);
    const log = person.days[String(d)] ?? null;
    const off = person.offs[String(d)] ?? null;
    const c = contractOn(d);
    const acc = spanOn(person.accounts, iso);
    const f = forms[d] ?? init[d] ?? EMPTY_FORM;
    const dirty = !sameForm(f, init[d] ?? EMPTY_FORM);
    const wd = new Date(`${iso}T00:00:00Z`).getUTCDay();
    const isOff = f.off !== "";
    return {
      d, iso, wd, log, off, c, acc, f, dirty, isOff,
      weekend: wd === 0 || wd === 6, work: isWorkday(c, iso), miss: !dirty && missing.has(d),
      del: dirty && !!log && f.out === "",          // 근무 삭제 (휴무로 전환 포함)
      offDel: dirty && !!off && !isOff,             // 휴무 해제
      future: iso > today, pv: preview(c, f),
    };
  }), [forms, init, person, lastDay, month, today, missing]);

  const locked = !isAdmin || closed;
  const multi = person.contracts.filter((s) => s.contract).length > 1;   // 월 중 계약 변경자만 날짜별 지정 칸
  const saves = rows.filter((r) => r.dirty && !r.isOff && r.f.out !== "");
  const dels = rows.filter((r) => r.del);
  const offSaves = rows.filter((r) => r.dirty && r.isOff);
  const offDels = rows.filter((r) => r.offDel);
  const blocked = saves.filter((r) => r.pv.err || !r.c || r.future);
  const needOut = rows.filter((r) => r.dirty && !r.log && !r.isOff && !r.offDel && r.f.out === "");
  const dirtyCount = rows.filter((r) => r.dirty).length;
  const worked = rows.filter((r) => !r.isOff && r.f.out !== "" && r.pv.paid != null);
  const paidSum = worked.reduce((a, r) => a + (r.pv.paid ?? 0), 0);
  const wkCount = worked.filter((r) => r.weekend).length;
  const offCount = rows.filter((r) => r.isOff).length;
  const missCount = rows.filter((r) => r.miss).length;
  const nothing = saves.length + dels.length + offSaves.length + offDels.length === 0;
  const saveLabel = [
    saves.length && `근무 ${num(saves.length)}`, dels.length && `근무 삭제 ${num(dels.length)}`,
    offSaves.length && `휴무 ${num(offSaves.length)}`, offDels.length && `휴무 해제 ${num(offDels.length)}`,
  ].filter(Boolean).join(" · ");
  const sortedManagers = useMemo(
    () => managers.filter((x) => x.name).sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true })),
    [managers],
  );

  // 처음 열 때: 날짜 칸 클릭 = 그날, 이름 클릭 = 첫 미입력일 → 없으면 퇴근이 비어 있는 첫 근무일
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const d = focusDay ?? person.missing_days[0]
        ?? rows.find((r) => !locked && !r.future && r.c && r.work && !r.isOff && r.f.out === "")?.d ?? null;
      if (d == null) return;
      rowRefs.current[d]?.scrollIntoView({ block: "nearest" });
      outRefs.current[d]?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [focusDay]);

  const set = (d: number, patch: Partial<LogForm>) =>
    setForms((s) => ({ ...s, [d]: { ...(s[d] ?? init[d] ?? EMPTY_FORM), ...patch } }));

  /** 근무/휴무 칸: 휴무 선택 = 시간 비움, '근무'로 되돌리면 원래 기록 복원 */
  function setOff(d: number, v: string) {
    const base = init[d] ?? EMPTY_FORM;
    const c = contractOn(d);
    if (v === "") set(d, base.off === "" ? { ...base } : { off: "" });
    else set(d, { off: v, out: "", punch: defaultIn(c), brk: c ? String(defaultBreak(c)) : "" });
  }

  function next(d: number) {
    for (let k = d + 1; k <= lastDay; k++) {
      const el = outRefs.current[k];
      if (el && !el.disabled) { el.focus(); el.scrollIntoView({ block: "nearest" }); return; }
    }
  }

  function fillWorkdays() {
    const targets = rows.filter((r) => !r.log && !r.isOff && !r.future && r.c?.work_end && r.work && r.f.out === "");
    if (targets.length === 0) { alert("채울 빈 근무일이 없습니다."); return; }
    if (!confirm(`빈 근무일(계약 근무 요일) ${targets.length}일에 지정 퇴근 시각을 채웁니다.\n쉰 날은 근무/휴무 칸에서 휴무로 바꾸고, 실제와 다른 날만 고치세요.`)) return;
    setForms((s) => {
      const o = { ...s };
      for (const r of targets) o[r.d] = { ...(o[r.d] ?? init[r.d] ?? EMPTY_FORM), out: r.c!.work_end! };
      return o;
    });
  }

  function close() {
    if (dirtyCount > 0 && !confirm(`저장하지 않은 입력 ${dirtyCount}건이 있습니다. 취소하고 닫을까요?`)) return;
    onClose();
  }

  async function save() {
    if (nothing) return;
    setBusy(true);
    setError("");
    try {
      const items: WorkLogDateInput[] = saves.map(({ iso, c, f }) => ({ work_date: iso, ...toInput(c, f) }));
      const offs: WorkOffInput[] = offSaves.map(({ iso, f }) => ({
        work_date: iso, reason: f.off as OffReason, memo: f.memo.trim() || null }));
      const r = await saveWorkPerson(person.worker_id, items, dels.map((x) => x.log!.id), offs, offDels.map((x) => x.off!.id));
      const parts = [`근무 저장 ${num(r.saved)}건`];
      if (r.deleted) parts.push(`근무 삭제 ${num(r.deleted)}건`);
      if (r.off_saved) parts.push(`휴무 지정 ${num(r.off_saved)}건`);
      if (r.off_deleted) parts.push(`휴무 해제 ${num(r.off_deleted)}건`);
      if (r.unchanged) parts.push(`기존과 같아 건너뜀 ${num(r.unchanged)}건`);
      const w = Object.entries(r.warns).map(([k, v]) => `${k} ${v.join(", ")}`);
      onSaved(`${person.name}: ${parts.join(" · ")}${w.length ? ` · ⚠ ${w.join(" / ")}` : ""}`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const statusOf = (r: (typeof rows)[number]) => {
    if (r.isOff) {
      if (!r.dirty) return <Chip>휴무 · {OFF_LABEL[r.f.off as OffReason]}</Chip>;
      return <Chip tone="caution">{r.log ? "근무→휴무" : r.off ? "휴무 수정" : "휴무 지정"} · 저장 전</Chip>;
    }
    if (r.offDel) return <Chip tone="caution">{r.f.out ? "휴무→근무" : "휴무 해제"} · 저장 전</Chip>;
    if (r.del) return <Chip tone="caution">삭제 · 저장 전</Chip>;
    if (r.dirty && !r.log && r.f.out === "") return <Chip tone="danger">퇴근 필요</Chip>;
    if (r.dirty) return <Chip tone="caution">{r.log ? "수정 · 저장 전" : "새 입력 · 저장 전"}</Chip>;
    if (r.log) return <Chip tone="ok">저장됨</Chip>;
    if (r.future) return <span className="muted small">미래</span>;
    if (r.miss) return <Chip tone="caution">미입력</Chip>;
    if (r.c && !r.work) return <span className="muted small">쉬는 요일</span>;
    return null;
  };

  const contractsText = person.contracts
    .filter((s) => s.contract)
    .map((s, i) => `${i === 0 ? "" : `${Number(s.from.slice(5, 7))}/${Number(s.from.slice(8))}~ `}${contractText(s.contract)}`)
    .join(" / ");

  return (
    <Modal open size="full" onClose={close}
      title={<>{person.name} <span className="muted small">{INCOME_LABEL[person.income_type]}</span> · {y}년 {m}월 근무 기록</>}
      footer={<>
        <span className="muted small wp-sum">
          입력 기준 근무 {num(worked.length)}일{wkCount > 0 ? ` (주말 ${num(wkCount)}일)` : ""} · 유급 {hmm(paidSum)} · 휴무 {num(offCount)}일
          {missCount > 0 && <> · <b className="wl-bad-text">미입력 {missCount}일</b></>}
          {blocked.length > 0 && <> · <b className="wl-bad-text">저장 불가 {blocked.length}건</b></>}
          {needOut.length > 0 && <> · <b className="wl-bad-text">퇴근 입력 필요 {needOut.length}건</b></>}
        </span>
        <Button onClick={close}>닫기</Button>
        {!locked && (
          <Button variant="primary" onClick={save}
            disabled={busy || nothing || blocked.length > 0 || needOut.length > 0}>
            {busy ? "저장 중…" : nothing ? "저장할 입력 없음" : `저장 (${saveLabel})`}
          </Button>
        )}
      </>}
    >
      {error && <ErrorBox message={error} />}
      <div className="wp-tools">
        <span className="small">지정 근무: <b>{contractsText || "계약 없음"}</b></span>
        {closed && <Chip tone="warn">마감된 달 · 수정 불가</Chip>}
        {!isAdmin && <Chip>조회 전용</Chip>}
        {!locked && <>
          <Button size="sm" onClick={fillWorkdays}>빈 근무일 → 지정 퇴근 채우기</Button>
          <Button size="sm" variant="ghost" disabled={dirtyCount === 0} onClick={() => setForms(init)}>저장 전 입력 취소</Button>
        </>}
        <span className="muted small wp-help"
          title="출근·휴게는 계약 기본값(회색)이 채워져 있고 그대로 두면 계약을 따릅니다. 쉰 날은 근무/휴무 칸에서 사유를 고르세요(엑셀에는 안 들어감). 토·일 근무는 주말 근무로 따로 집계됩니다.">
          퇴근만 입력 → Enter = 다음 날 · <span className="wl-def-sample">회색</span> = 계약 기본값 · 퇴근 지우면 삭제 · 쉰 날 = 휴무 사유 선택
        </span>
      </div>
      <div className="wp-wrap">
        <table className="tbl wp-tbl">
          <colgroup>
            <col className="wp-c-day" /><col className="wp-c-off" />
            {multi && <col className="wp-c-con" />}
            <col className="wp-c-in" /><col className="wp-c-out" /><col className="wp-c-brk" />
            <col className="wp-c-acc" /><col /><col className="wp-c-paid" /><col className="wp-c-st" />
          </colgroup>
          <thead>
            <tr>
              <th>날짜</th><th>근무/휴무</th>{multi && <th>지정</th>}<th>출근(지문)</th><th>퇴근(지문)</th><th>휴게(분)</th>
              <th>그날 계정</th><th>메모</th><th className="num">유급</th><th>상태</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const dis = locked || r.future || !r.c || r.isOff;
              const memoDis = locked || (!r.isOff && (r.future || !r.c));
              const cls = [r.wd === 0 ? "wp-sun" : r.wd === 6 ? "wp-sat" : "", r.d === focusDay ? "wp-focus" : "",
                r.dirty ? "wl-dirty" : "", r.future ? "off" : "", r.isOff ? "wp-off" : "", r.miss ? "wp-miss" : ""]
                .filter(Boolean).join(" ");
              return (
                <tr key={r.d} ref={(el) => { rowRefs.current[r.d] = el; }} className={cls || undefined}>
                  <td>{r.d}일 ({WD[r.wd]}){r.weekend && !r.isOff && r.f.out !== "" && <> <Chip>주말</Chip></>}</td>
                  <td>
                    <select className="input input-sm wl-sel" value={r.f.off} disabled={locked}
                      onChange={(e) => setOff(r.d, e.target.value)}>
                      <option value="">근무</option>
                      {OFF_REASONS.map(([k, l]) => <option key={k} value={k}>휴무 · {l}</option>)}
                    </select>
                  </td>
                  {multi && <td className="small">{r.c ? contractText(r.c) : <Chip tone="danger">계약 없음</Chip>}</td>}
                  <td>
                    <div className="wp-in">
                      <input type="time" className={`input input-sm wl-time${isDefaultIn(r.c, r.f.punch) ? " wl-def" : ""}`}
                        value={r.isOff ? "" : r.f.punch} disabled={dis}
                        onChange={(e) => set(r.d, { punch: e.target.value })}
                        onBlur={() => { if (!r.f.punch) set(r.d, { punch: defaultIn(r.c) }); }} />
                      {!r.c && !multi && !r.isOff && <Chip tone="danger">계약 없음</Chip>}
                      {!r.isOff && r.pv.cin != null && toMin(r.f.punch) !== r.pv.cin && <span className="wp-note">인정 {hmm(r.pv.cin)}</span>}
                    </div>
                  </td>
                  <td>
                    <input type="time" className="input input-sm wl-time" value={r.f.out} disabled={dis}
                      ref={(el) => { outRefs.current[r.d] = el; }}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); next(r.d); } }}
                      onChange={(e) => set(r.d, { out: e.target.value })} />
                  </td>
                  <td>
                    <input type="number" min={0} max={600} className={`input input-sm wl-num${isDefaultBreak(r.c, r.f.brk) ? " wl-def" : ""}`}
                      value={r.isOff ? "" : r.f.brk} disabled={dis}
                      onChange={(e) => set(r.d, { brk: e.target.value })}
                      onBlur={() => { if (r.f.brk === "" && r.c) set(r.d, { brk: String(defaultBreak(r.c)) }); }} />
                  </td>
                  <td>
                    <select className="input input-sm wl-sel" value={r.f.mid} disabled={dis}
                      onChange={(e) => set(r.d, { mid: e.target.value })}>
                      <option value="">고정: {r.acc?.manager_name ?? "없음"}</option>
                      {sortedManagers.map((x) => <option key={x.manager_id} value={x.manager_id}>{x.name}</option>)}
                    </select>
                  </td>
                  <td>
                    <input className="input input-sm wl-memo" value={r.f.memo} maxLength={200} disabled={memoDis}
                      placeholder={r.isOff ? "휴무 메모" : undefined}
                      onChange={(e) => set(r.d, { memo: e.target.value })} />
                  </td>
                  <td className="num">{r.isOff ? "" : r.pv.err ? <Chip tone="danger">{r.pv.err}</Chip> : r.f.out ? hmm(r.pv.paid) : ""}</td>
                  <td>{statusOf(r)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}
