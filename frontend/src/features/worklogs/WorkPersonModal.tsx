import { useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import type { ManagerRow } from "@/api/masters";
import { INCOME_LABEL } from "@/api/workers";
import { hmm, saveWorkPerson, spanOn, toMin } from "@/api/worklogs";
import type { WorkLogDateInput, WorkMonthPerson } from "@/api/worklogs";
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

/** 월 표에서 한 사람의 한 달 근무 입력 (이름 클릭 = 전체, 날짜 칸 클릭 = 그날로 이동). 화면 가득, 가로 스크롤 없음 */
export default function WorkPersonModal({ person, month, lastDay, focusDay, closed, isAdmin, managers, onClose, onSaved }: Props) {
  const today = todayKst();
  const [y, m] = month.split("-").map(Number);
  const contractOn = (d: number) => spanOn(person.contracts, isoOf(month, d))?.contract ?? null;
  const init = useMemo(() => {
    const o: Record<number, LogForm> = {};
    for (let d = 1; d <= lastDay; d++) o[d] = logToForm(person.days[String(d)] ?? null, contractOn(d));
    return o;
  }, [person, lastDay, month]);
  const [forms, setForms] = useState<Record<number, LogForm>>(init);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const outRefs = useRef<Record<number, HTMLInputElement | null>>({});
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({});

  useEffect(() => { setForms(init); }, [init]);

  const rows = useMemo(() => Array.from({ length: lastDay }, (_, i) => {
    const d = i + 1;
    const iso = isoOf(month, d);
    const log = person.days[String(d)] ?? null;
    const c = contractOn(d);
    const acc = spanOn(person.accounts, iso);
    const f = forms[d] ?? init[d] ?? EMPTY_FORM;
    const dirty = !sameForm(f, init[d] ?? EMPTY_FORM);
    return {
      d, iso, wd: new Date(`${iso}T00:00:00Z`).getUTCDay(), log, c, acc, f, dirty,
      del: dirty && !!log && f.out === "", future: iso > today, pv: preview(c, f),
    };
  }), [forms, init, person, lastDay, month, today]);

  const locked = !isAdmin || closed;
  const multi = person.contracts.filter((s) => s.contract).length > 1;   // 월 중 계약 변경자만 날짜별 지정 칸
  const saves = rows.filter((r) => r.dirty && r.f.out !== "");
  const dels = rows.filter((r) => r.del);
  const blocked = saves.filter((r) => r.pv.err || !r.c || r.future);
  const dirtyCount = rows.filter((r) => r.dirty).length;
  const worked = rows.filter((r) => r.f.out !== "" && r.pv.paid != null);
  const paidSum = worked.reduce((a, r) => a + (r.pv.paid ?? 0), 0);
  const sortedManagers = useMemo(
    () => managers.filter((x) => x.name).sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true })),
    [managers],
  );

  // 처음 열 때: 날짜 칸 클릭 = 그날, 이름 클릭 = 퇴근이 비어 있는 첫날
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const d = focusDay ?? rows.find((r) => !locked && !r.future && r.c && r.f.out === "")?.d ?? null;
      if (d == null) return;
      rowRefs.current[d]?.scrollIntoView({ block: "nearest" });
      outRefs.current[d]?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [focusDay]);

  const set = (d: number, patch: Partial<LogForm>) =>
    setForms((s) => ({ ...s, [d]: { ...(s[d] ?? init[d] ?? EMPTY_FORM), ...patch } }));

  function next(d: number) {
    for (let k = d + 1; k <= lastDay; k++) {
      const el = outRefs.current[k];
      if (el && !el.disabled) { el.focus(); el.scrollIntoView({ block: "nearest" }); return; }
    }
  }

  function fillWeekdays() {
    const targets = rows.filter((r) => !r.log && !r.future && r.c?.work_end && r.wd >= 1 && r.wd <= 5 && r.f.out === "");
    if (targets.length === 0) { alert("채울 빈 평일이 없습니다."); return; }
    if (!confirm(`빈 평일 ${targets.length}일에 지정 퇴근 시각을 채웁니다. 저장 전에 실제와 다른 날만 고치세요.`)) return;
    setForms((s) => {
      const o = { ...s };
      for (const r of targets) o[r.d] = { ...(o[r.d] ?? init[r.d] ?? EMPTY_FORM), out: r.c!.work_end! };
      return o;
    });
  }

  function close() {
    if (dirtyCount > 0 && !confirm(`저장하지 않은 변경 ${dirtyCount}건이 있습니다. 버리고 닫을까요?`)) return;
    onClose();
  }

  async function save() {
    if (saves.length === 0 && dels.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const items: WorkLogDateInput[] = saves.map(({ iso, c, f }) => ({ work_date: iso, ...toInput(c, f) }));
      const r = await saveWorkPerson(person.worker_id, items, dels.map((x) => x.log!.id));
      const w = Object.entries(r.warns).map(([k, v]) => `${k} ${v.join(", ")}`);
      onSaved(`${person.name}: 저장 ${num(r.saved)}건${r.deleted ? ` · 삭제 ${num(r.deleted)}건` : ""}`
        + `${r.unchanged ? ` · 변경 없음 ${num(r.unchanged)}건` : ""}${w.length ? ` · ⚠ ${w.join(" / ")}` : ""}`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const contractsText = person.contracts
    .filter((s) => s.contract)
    .map((s, i) => `${i === 0 ? "" : `${Number(s.from.slice(5, 7))}/${Number(s.from.slice(8))}~ `}${contractText(s.contract)}`)
    .join(" / ");

  return (
    <Modal open size="full" onClose={close}
      title={<>{person.name} <span className="muted small">{INCOME_LABEL[person.income_type]}</span> · {y}년 {m}월 근무 기록</>}
      footer={<>
        <span className="muted small wp-sum">
          입력 기준 근무 {num(worked.length)}일 · 유급 {hmm(paidSum)}
          {blocked.length > 0 && <> · <b className="wl-bad-text">저장 불가 {blocked.length}건</b></>}
        </span>
        <Button onClick={close}>닫기</Button>
        {!locked && (
          <Button variant="primary" onClick={save}
            disabled={busy || (saves.length === 0 && dels.length === 0) || blocked.length > 0}>
            {busy ? "저장 중…" : `변경 ${num(saves.length)}건${dels.length ? ` · 삭제 ${num(dels.length)}건` : ""} 저장`}
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
          <Button size="sm" onClick={fillWeekdays}>빈 평일 → 지정 퇴근 채우기</Button>
          <Button size="sm" variant="ghost" disabled={dirtyCount === 0} onClick={() => setForms(init)}>변경 되돌리기</Button>
        </>}
        <span className="muted small wp-help"
          title="출근·휴게는 계약 기본값(회색)이 채워져 있고 그대로 두면 계약을 따릅니다. 지문 출근이 지정보다 늦은 날·휴게가 다른 날만 고치세요. 저장된 날의 퇴근을 지우면 삭제됩니다.">
          퇴근만 입력 → Enter = 다음 날 · <span className="wl-def-sample">회색</span> = 계약 기본값 · 퇴근 지우면 삭제
        </span>
      </div>
      <div className="wp-wrap">
        <table className="tbl wp-tbl">
          <colgroup>
            <col className="wp-c-day" />
            {multi && <col className="wp-c-con" />}
            <col className="wp-c-in" /><col className="wp-c-out" /><col className="wp-c-brk" />
            <col className="wp-c-acc" /><col /><col className="wp-c-paid" /><col className="wp-c-st" />
          </colgroup>
          <thead>
            <tr>
              <th>날짜</th>{multi && <th>지정</th>}<th>출근(지문)</th><th>퇴근(지문)</th><th>휴게(분)</th>
              <th>그날 계정</th><th>메모</th><th className="num">유급</th><th>상태</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const dis = locked || r.future || !r.c;
              const cls = [r.wd === 0 ? "wp-sun" : r.wd === 6 ? "wp-sat" : "", r.d === focusDay ? "wp-focus" : "",
                r.dirty ? "wl-dirty" : "", r.future ? "off" : ""].filter(Boolean).join(" ");
              return (
                <tr key={r.d} ref={(el) => { rowRefs.current[r.d] = el; }} className={cls || undefined}>
                  <td>{r.d}일 ({WD[r.wd]})</td>
                  {multi && <td className="small">{r.c ? contractText(r.c) : <Chip tone="danger">계약 없음</Chip>}</td>}
                  <td>
                    <div className="wp-in">
                      <input type="time" className={`input input-sm wl-time${isDefaultIn(r.c, r.f.punch) ? " wl-def" : ""}`}
                        value={r.f.punch} disabled={dis}
                        onChange={(e) => set(r.d, { punch: e.target.value })}
                        onBlur={() => { if (!r.f.punch) set(r.d, { punch: defaultIn(r.c) }); }} />
                      {!r.c && !multi && <Chip tone="danger">계약 없음</Chip>}
                      {r.pv.cin != null && toMin(r.f.punch) !== r.pv.cin && <span className="wp-note">인정 {hmm(r.pv.cin)}</span>}
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
                      value={r.f.brk} disabled={dis}
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
                    <input className="input input-sm wl-memo" value={r.f.memo} maxLength={200} disabled={dis}
                      onChange={(e) => set(r.d, { memo: e.target.value })} />
                  </td>
                  <td className="num">{r.pv.err ? <Chip tone="danger">{r.pv.err}</Chip> : r.f.out ? hmm(r.pv.paid) : ""}</td>
                  <td>
                    {r.del ? <Chip tone="caution">삭제 예정</Chip>
                      : r.dirty ? <Chip tone="caution">변경</Chip>
                      : r.log ? <Chip tone="ok">저장됨</Chip>
                      : r.future ? <span className="muted small">미래</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}
