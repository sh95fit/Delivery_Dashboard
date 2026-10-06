import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import * as api from "@/api/workers";
import { INCOME_LABEL, INCOME_PAY } from "@/api/workers";
import type { AccountCandidate, ImportCommitRow, ImportPreview, IncomeType } from "@/api/workers";
import type { ManagerRow } from "@/api/masters";
import { errText, parseAmount } from "@/lib/form";
import { hm, num, todayKst } from "@/lib/format";

type Tab = "excel" | "accounts";
type Props = { managers: ManagerRow[]; onDone: (created: number) => Promise<void>; onClose: () => void };
type Edit = { sel: boolean; name: string; income: IncomeType; rate: string; ws: string; we: string; vat: boolean; mgr: string };
type ASel = { sel: boolean; name: string; income: IncomeType };

const INCOMES = Object.keys(INCOME_LABEL) as IncomeType[];
const monthStart = () => `${todayKst().slice(0, 7)}-01`;
const toB64 = (f: File) =>
  new Promise<string>((ok, ng) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] ?? "");
    r.onerror = () => ng(new Error("파일을 읽지 못했습니다"));
    r.readAsDataURL(f);
  });
const A_LABEL: Record<AccountCandidate["status"], string> = {
  new: "신규", shared: "공용·테스트 추정", exists: "같은 이름 등록됨", held: "사용 중",
};

export default function WorkerImport({ managers, onDone, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("excel");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // 엑셀
  const [file, setFile] = useState<File | null>(null);
  const [fileIncome, setFileIncome] = useState<"employee" | "business">("employee");
  const [prev, setPrev] = useState<ImportPreview | null>(null);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [from, setFrom] = useState(monthStart());
  const [brk, setBrk] = useState("0");
  const [brkPaid, setBrkPaid] = useState(true);
  const [otMin, setOtMin] = useState("");
  const [otAmt, setOtAmt] = useState("");

  // 운영 계정
  const [cands, setCands] = useState<AccountCandidate[] | null>(null);
  const [aSel, setASel] = useState<Record<number, ASel>>({});
  const [aFrom, setAFrom] = useState(monthStart());

  const mgrOptions = useMemo(() => [...managers].sort((a, b) =>
    Number(b.ops_status === "active") - Number(a.ops_status === "active") ||
    (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true })), [managers]);

  useEffect(() => {
    if (tab !== "accounts" || cands) return;
    api.importAccountCandidates()
      .then((r) => {
        setCands(r.items);
        setASel(Object.fromEntries(r.items.map((c) => [c.manager_id, { sel: c.status === "new", name: c.name, income: "employee" as IncomeType }])));
      })
      .catch((e) => setError(errText(e)));
  }, [tab, cands]);

  async function readFile() {
    if (!file) return setError("파일을 선택하세요");
    setBusy(true);
    setError("");
    try {
      const p = await api.previewImportExcel({ file_name: file.name, content_b64: await toB64(file), file_income: fileIncome });
      setPrev(p);
      setEdits(p.rows.map((r) => ({
        sel: r.status === "new", name: r.name, income: r.income_type, rate: r.rate ? String(r.rate) : "",
        ws: r.work_start ?? "", we: r.work_end ?? "", vat: r.has_vat, mgr: r.manager_id != null ? String(r.manager_id) : "",
      })));
      if (p.rows[0]?.month) setFrom(p.rows[0].month);
    } catch (e) {
      setError(errText(e));
      setPrev(null);
    } finally {
      setBusy(false);
    }
  }
  const upd = (i: number, patch: Partial<Edit>) => setEdits((es) => es.map((e, k) => (k === i ? { ...e, ...patch } : e)));

  function excelRows(): ImportCommitRow[] | string {
    const um = Number(otMin) || 0;
    const ua = otAmt.trim() ? parseAmount(otAmt) : 0;
    if (Number.isNaN(ua) || (um > 0) !== (ua > 0)) return "초과수당 단위(분)와 금액은 둘 다 입력하거나 둘 다 비워 두세요";
    const out: ImportCommitRow[] = [];
    for (let i = 0; i < edits.length; i++) {
      const e = edits[i];
      if (!e.sel) continue;
      const amt = parseAmount(e.rate);
      const pt = INCOME_PAY[e.income];
      const label = e.name.trim() || `${i + 1}번째 행`;
      if (!e.name.trim()) return `${label}: 이름을 입력하세요`;
      if (Number.isNaN(amt) || amt <= 0) return `${label}: 금액을 확인하세요`;
      if (pt === "hourly" && (!e.ws || !e.we)) return `${label}: 지정 출근·퇴근을 입력하세요`;
      out.push({
        name: e.name.trim(), income_type: e.income, manager_id: e.mgr ? Number(e.mgr) : null, account_from: from,
        rate: {
          effective_from: from, pay_type: pt, amount: amt, vat_applied: e.vat, memo: "근무표 일괄 등록",
          ...(pt === "hourly" ? { work_start: e.ws, work_end: e.we, break_min: Number(brk) || 0, break_paid: brkPaid,
            ot_unit_min: um, ot_unit_amount: ua } : {}),
        },
      });
    }
    return out.length ? out : "등록할 행을 선택하세요";
  }

  function accountRows(): ImportCommitRow[] | string {
    const out: ImportCommitRow[] = (cands ?? [])
      .filter((c) => aSel[c.manager_id]?.sel)
      .map((c) => ({ name: aSel[c.manager_id].name.trim(), income_type: aSel[c.manager_id].income,
        manager_id: c.manager_id, account_from: aFrom }));
    if (out.some((r) => !r.name)) return "이름이 빈 행이 있습니다";
    return out.length ? out : "등록할 계정을 선택하세요";
  }

  async function commit(rows: ImportCommitRow[] | string) {
    if (typeof rows === "string") return setError(rows);
    if (!window.confirm(`${rows.length}명을 등록할까요?\n한 건이라도 오류가 있으면 아무것도 저장되지 않습니다.`)) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.commitImport(rows);
      await onDone(res.created);
      onClose();
    } catch (e) {
      setError(errText(e));
      setBusy(false);
    }
  }

  const selCount = tab === "excel" ? edits.filter((e) => e.sel).length
    : Object.values(aSel).filter((a) => a.sel).length;

  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title="인력 일괄 등록"
      footer={
        <>
          <Button onClick={onClose}>닫기</Button>
          <Button variant="primary" disabled={busy || selCount === 0}
            onClick={() => commit(tab === "excel" ? excelRows() : accountRows())}>
            {busy ? "처리 중…" : `${num(selCount)}명 등록`}
          </Button>
        </>
      }
    >
      <div className="seg">
        <button type="button" className={tab === "excel" ? "on" : undefined} onClick={() => setTab("excel")}>근무표 엑셀 (시급제)</button>
        <button type="button" className={tab === "accounts" ? "on" : undefined} onClick={() => setTab("accounts")}>운영 계정 (정규직·개인 계정)</button>
      </div>
      {error && <div className="stack mt"><ErrorBox message={error} /></div>}

      {tab === "excel" ? (
        <>
          <div className="form-grid mt">
            <label className="field field-wide">근무표 파일 (.xlsx)
              <input type="file" className="input" accept=".xlsx"
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPrev(null); }} />
            </label>
            <label className="field">파일 종류
              <select className="input" value={fileIncome} onChange={(e) => setFileIncome(e.target.value as "employee" | "business")}>
                <option value="employee">근로소득 근무표</option>
                <option value="business">사업소득 근무표</option>
              </select>
            </label>
            <div className="form-actions">
              <Button variant="primary" disabled={busy || !file} onClick={readFile}>{busy && !prev ? "읽는 중…" : "미리보기"}</Button>
            </div>
          </div>
          <p className="muted small">
            이름·시급·시간대(지정 출퇴근)·부가세 열을 읽어 채웁니다. 이미 등록된 이름은 건너뜁니다.
            근무표 안의 시간 오류는 등록에 영향이 없고, 근무 기록 업로드 단계에서 다시 검사합니다.
          </p>

          {busy && !prev && <Spinner />}
          {prev && (
            <>
              <div className="kv-line mt">
                {prev.sheets.map((s) => (
                  <span key={s.sheet}>
                    {s.skipped
                      ? <Chip>{s.sheet}: 건너뜀{s.msg ? ` (${s.msg})` : ""}</Chip>
                      : <Chip tone={s.errors ? "caution" : "ok"}>{s.sheet} · {s.month?.slice(0, 7)} · {num(s.people)}명{s.errors ? ` · 근무표 오류 ${num(s.errors)}` : ""}</Chip>}
                  </span>
                ))}
              </div>

              <div className="form-grid mt">
                <label className="field">적용 시작일 (계약·계정)
                  <input type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} />
                </label>
                <label className="field">휴게(분, 공통)
                  <input className="input" inputMode="numeric" value={brk} onChange={(e) => setBrk(e.target.value)} />
                </label>
                <label className="field">휴게 처리
                  <select className="input" value={brkPaid ? "1" : "0"} onChange={(e) => setBrkPaid(e.target.value === "1")}>
                    <option value="1">유급</option>
                    <option value="0">무급</option>
                  </select>
                </label>
                <label className="field">초과수당 단위(분, 공통)
                  <input className="input" inputMode="numeric" value={otMin} onChange={(e) => setOtMin(e.target.value)} placeholder="비우면 없음" />
                </label>
                <label className="field">단위당 금액(원)
                  <input className="input" inputMode="numeric" value={otAmt} onChange={(e) => setOtAmt(e.target.value)} placeholder="예: 5,000" />
                </label>
              </div>

              <DataTable columns={["", "이름", "구분", "금액", "지정 출근", "지정 퇴근", "부가세", "고정 계정", "근무", "확인"]}>
                {prev.rows.map((r, i) => {
                  const e = edits[i];
                  const off = r.status !== "new";
                  return (
                    <tr key={`${r.sheet}-${r.row}`} className={off ? "off" : undefined}>
                      <td><input type="checkbox" checked={e.sel} disabled={off} onChange={(ev) => upd(i, { sel: ev.target.checked })} /></td>
                      <td><input className="input input-sm" value={e.name} disabled={off} onChange={(ev) => upd(i, { name: ev.target.value })} /></td>
                      <td>
                        <select className="input input-sm" value={e.income} disabled={off} onChange={(ev) => upd(i, { income: ev.target.value as IncomeType })}>
                          {INCOMES.map((k) => <option key={k} value={k}>{INCOME_LABEL[k]}</option>)}
                        </select>
                      </td>
                      <td><input className="input input-sm" inputMode="numeric" value={e.rate} disabled={off} onChange={(ev) => upd(i, { rate: ev.target.value })} /></td>
                      <td><input type="time" className="input input-sm" value={e.ws} disabled={off} onChange={(ev) => upd(i, { ws: ev.target.value })} /></td>
                      <td><input type="time" className="input input-sm" value={e.we} disabled={off} onChange={(ev) => upd(i, { we: ev.target.value })} /></td>
                      <td><input type="checkbox" checked={e.vat} disabled={off} onChange={(ev) => upd(i, { vat: ev.target.checked })} /></td>
                      <td>
                        <select className="input input-sm" value={e.mgr} disabled={off} onChange={(ev) => upd(i, { mgr: ev.target.value })}>
                          <option value="">없음</option>
                          {mgrOptions.map((m) => (
                            <option key={m.manager_id} value={m.manager_id}>
                              {m.name ?? `#${m.manager_id}`}{m.ops_status !== "active" ? " (비활성)" : ""}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="muted small">{num(r.days)}일 · {hm(r.minutes)}</td>
                      <td className="small">
                        {r.status === "new" ? <Chip tone="ok">신규</Chip> : r.status === "exists" ? <Chip>등록됨</Chip> : <Chip tone="caution">제외</Chip>}
                        {r.flags.map((f) => <div key={f} className="muted">{f}</div>)}
                      </td>
                    </tr>
                  );
                })}
              </DataTable>
            </>
          )}
        </>
      ) : (
        <>
          <div className="form-grid mt">
            <label className="field">고정 계정 시작일
              <input type="date" className="input" value={aFrom} onChange={(e) => setAFrom(e.target.value)} />
            </label>
          </div>
          <p className="muted small">
            운영 활성 계정 중 개인 이름 계정을 인력으로 등록하고 그 계정을 고정 배정합니다. 공용·테스트로 보이는 계정은 기본 해제입니다.
            계약 조건은 등록 후 인력별로 입력하세요(정규직은 월급, 그 외는 시급·지정 출퇴근).
          </p>
          {!cands ? <Spinner /> : cands.length === 0 ? (
            <div className="muted small">운영 활성 계정이 없습니다.</div>
          ) : (
            <DataTable columns={["", "운영 계정", "인력 이름", "구분", "상태"]}>
              {cands.map((c) => {
                const s = aSel[c.manager_id];
                const off = c.status === "exists" || c.status === "held";
                return (
                  <tr key={c.manager_id} className={off ? "off" : undefined}>
                    <td><input type="checkbox" checked={!!s?.sel} disabled={off}
                      onChange={(ev) => setASel((m) => ({ ...m, [c.manager_id]: { ...m[c.manager_id], sel: ev.target.checked } }))} /></td>
                    <td><span className="dot" style={{ background: c.color ?? "#9ca3af" }} /> {c.name || `#${c.manager_id}`}</td>
                    <td><input className="input input-sm" value={s?.name ?? ""} disabled={off}
                      onChange={(ev) => setASel((m) => ({ ...m, [c.manager_id]: { ...m[c.manager_id], name: ev.target.value } }))} /></td>
                    <td>
                      <select className="input input-sm" value={s?.income ?? "employee"} disabled={off}
                        onChange={(ev) => setASel((m) => ({ ...m, [c.manager_id]: { ...m[c.manager_id], income: ev.target.value as IncomeType } }))}>
                        {INCOMES.map((k) => <option key={k} value={k}>{INCOME_LABEL[k]}</option>)}
                      </select>
                    </td>
                    <td>
                      {c.status === "new" ? <Chip tone="ok">{A_LABEL.new}</Chip>
                        : c.status === "shared" ? <Chip tone="caution">{A_LABEL.shared}</Chip>
                        : <Chip>{c.status === "held" ? `${c.holder ?? ""} ${A_LABEL.held}` : A_LABEL.exists}</Chip>}
                    </td>
                  </tr>
                );
              })}
            </DataTable>
          )}
        </>
      )}
    </Modal>
  );
}
