import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { INCOME_LABEL } from "@/api/workers";
import { downloadTimesheet, getExportPlan, hmm } from "@/api/worklogs";
import type { ExportKind, ExportPlan, ExportQuery, SheetKind, WorkMonthPerson } from "@/api/worklogs";
import { errText } from "@/lib/form";
import { num, won } from "@/lib/format";

const KINDS: Array<[ExportKind, string]> = [["all", "전체 (두 파일)"], ["labor", "근로소득"], ["business", "사업소득"]];
const SHEET_NAME: Record<SheetKind, string> = { labor: "근로소득", business: "사업소득" };
const LEVEL: Record<string, string> = { error: "오류", warn: "확인", info: "안내" };

type Props = { month: string; lastDay: number; people: WorkMonthPerson[]; onClose: () => void };

/** 근무표 엑셀 다운로드: 구분 × 대상(전체·선택) × 기간 → 서버 점검 → 받기 */
export default function ExportModal({ month, lastDay, people, onClose }: Props) {
  const first = `${month}-01`;
  const last = `${month}-${String(lastDay).padStart(2, "0")}`;
  const [y, m] = month.split("-").map(Number);
  const [kind, setKind] = useState<ExportKind>("all");
  const [pick, setPick] = useState(false);
  const [ids, setIds] = useState<Set<number>>(new Set());
  const [whole, setWhole] = useState(true);
  const [start, setStart] = useState(first);
  const [end, setEnd] = useState(last);
  const [plan, setPlan] = useState<ExportPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");

  // 정규직(sheet 없음)은 근무표 대상 아님
  const cands = useMemo(
    () => people.filter((p) => p.sheet && (kind === "all" || p.sheet === kind))
      .sort((a, b) => a.name.localeCompare(b.name, "ko")),
    [people, kind],
  );
  const chosen = cands.filter((p) => ids.has(p.worker_id)).map((p) => p.worker_id);
  const badRange = !whole && !(first <= start && start <= end && end <= last);
  const noPick = pick && chosen.length === 0;   // 서버는 ids가 비면 '전체'로 처리 → 화면에서 막음
  const q: ExportQuery = {
    month: first, sheet: kind,
    start: whole ? undefined : start, end: whole ? undefined : end,
    ids: pick ? chosen : undefined,
  };
  const qKey = JSON.stringify(q);

  useEffect(() => {
    setDone("");
    if (badRange || noPick) { setPlan(null); setError(""); return; }
    let alive = true;
    setLoading(true);
    getExportPlan(q)
      .then((p) => { if (alive) { setPlan(p); setError(""); } })
      .catch((e) => { if (alive) { setPlan(null); setError(errText(e)); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [qKey, badRange, noPick]);

  const targets: SheetKind[] = kind === "all" ? ["labor", "business"] : [kind];
  const issues = (plan?.issues ?? []).filter((i) => i.sheet === null || targets.includes(i.sheet));
  const count = plan ? targets.reduce((a, s) => a + plan.sheets[s].length, 0) : 0;
  const hasError = issues.some((i) => i.level === "error");
  const can = !!plan && !loading && count > 0 && !hasError && !badRange && !noPick;

  function toggle(id: number) {
    setIds((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  async function download() {
    setBusy(true);
    setError("");
    try {
      setDone(await downloadTimesheet(q));
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open size="xl" onClose={onClose} title={`${y}년 ${m}월 근무표 다운로드`}
      footer={<>
        <span className="muted small ex-foot">
          {loading ? "점검 중…" : plan ? `대상 ${num(count)}명${hasError ? " · 오류가 있어 받을 수 없습니다" : ""}` : ""}
        </span>
        <Button onClick={onClose}>닫기</Button>
        <Button variant="primary" onClick={download} disabled={!can || busy}>
          {busy ? "만드는 중…" : kind === "all" ? "엑셀 받기 (근로·사업)" : `${SHEET_NAME[kind]} 엑셀 받기`}
        </Button>
      </>}
    >
      {error && <ErrorBox message={error} />}
      {done && <div className="notice">✓ {done} 받음</div>}

      <div className="ex-opts">
        <div className="ex-row">
          <span className="ex-label">구분</span>
          <div className="seg">
            {KINDS.map(([k, label]) => (
              <button key={k} type="button" className={kind === k ? "on" : undefined} onClick={() => setKind(k)}>{label}</button>
            ))}
          </div>
          <span className="muted small">전체 = 두 파일을 zip 하나로 (한쪽이 비면 엑셀 하나)</span>
        </div>

        <div className="ex-row">
          <span className="ex-label">대상</span>
          <div className="seg">
            <button type="button" className={!pick ? "on" : undefined} onClick={() => setPick(false)}>전체 인력</button>
            <button type="button" className={pick ? "on" : undefined} onClick={() => setPick(true)}>선택 인력</button>
          </div>
          {pick && <>
            <Button size="sm" variant="ghost" onClick={() => setIds(new Set(cands.map((p) => p.worker_id)))}>모두 선택</Button>
            <Button size="sm" variant="ghost" onClick={() => setIds(new Set())}>선택 해제</Button>
            <span className="muted small">{num(chosen.length)}명 선택</span>
          </>}
        </div>
        {pick && (cands.length === 0 ? (
          <div className="muted small">이 구분에 이 달 근무 기록·계약이 있는 인력이 없습니다.</div>
        ) : (
          <div className="ex-pick">
            {cands.map((p) => (
              <label key={p.worker_id}>
                <input type="checkbox" checked={ids.has(p.worker_id)} onChange={() => toggle(p.worker_id)} />
                {p.name} <span className="muted">{INCOME_LABEL[p.income_type]}</span>
                {!p.active && <Chip tone="caution">비활성</Chip>}
              </label>
            ))}
          </div>
        ))}
        {noPick && <div className="wl-block">인력을 1명 이상 고르세요.</div>}

        <div className="ex-row">
          <span className="ex-label">기간</span>
          <div className="seg">
            <button type="button" className={whole ? "on" : undefined} onClick={() => setWhole(true)}>한 달 전체</button>
            <button type="button" className={!whole ? "on" : undefined} onClick={() => setWhole(false)}>기간 지정</button>
          </div>
          {!whole && <>
            <input type="date" className="input input-sm" min={first} max={last} value={start} onChange={(e) => setStart(e.target.value)} />
            <span>~</span>
            <input type="date" className="input input-sm" min={first} max={last} value={end} onChange={(e) => setEnd(e.target.value)} />
          </>}
        </div>
        {badRange && <div className="wl-block">기간은 {m}월 안에서 시작일 ≤ 종료일로 고르세요 (근무표는 한 달 양식).</div>}
      </div>

      {loading && !plan ? <Spinner /> : plan && <>
        {issues.length > 0 && (
          <ul className="ex-issues">
            {issues.map((i, k) => (
              <li key={k} className={`ex-${i.level}`}>
                [{LEVEL[i.level]}] {i.sheet ? `${SHEET_NAME[i.sheet]} · ` : ""}{i.name ? `${i.name}: ` : ""}{i.msg}
              </li>
            ))}
          </ul>
        )}
        {targets.map((s) => (
          <div key={s}>
            <div className="group-title">{SHEET_NAME[s]} {num(plan.sheets[s].length)}명</div>
            {plan.sheets[s].length === 0 ? (
              <div className="muted small">대상 없음 (이 파일은 만들지 않습니다)</div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>이름</th><th>지정 근무</th><th className="num">시급</th><th className="num">근무일</th>
                    <th className="num">유급시간</th><th className="num">기본급</th><th className="num">수당</th>
                    <th className="num">근무표 지급</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.sheets[s].map((p) => (
                    <tr key={p.worker_id} className={p.active ? undefined : "off"}>
                      <td>{p.name}{!p.active && <span className="muted small"> 비활성</span>}</td>
                      <td className="small">{p.note || "-"}</td>
                      <td className="num">{won(p.rate)}</td>
                      <td className="num">{num(p.work_days)}</td>
                      <td className="num">{hmm(p.paid_min)}</td>
                      <td className="num">{won(p.base)}</td>
                      <td className="num">{p.incentive + p.weekend ? won(p.incentive + p.weekend) : "-"}</td>
                      <td className="num"><b>{won(p.sheet_total)}</b>{p.vat && <div className="muted small">부가세 포함</div>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </>}
    </Modal>
  );
}
