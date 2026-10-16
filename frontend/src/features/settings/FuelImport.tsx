import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import type { ChipTone } from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import * as fuel from "@/api/fuel";
import type { FuelImportPreview, FuelImportRow, ImportLevel } from "@/api/fuel";
import { FUEL_LABEL } from "@/api/masters";
import { errText } from "@/lib/form";
import { num, won } from "@/lib/format";

/* S3-P1b-2b-3b 주유 거래내역 엑셀 업로드 — 미리보기 → 끝번호별 차량 연결 · 행 선택 → 한 번에 저장 (업로드 기록에서 되돌리기) */

type Props = { onDone: (month: string | null) => Promise<void>; onClose: () => void };

const MAX_BYTES = 2 * 1024 * 1024;
const LEVELS: ImportLevel[] = ["ok", "warn", "need_vehicle", "error", "cancel"];
const LEVEL: Record<ImportLevel, [string, ChipTone]> = {
  ok: ["저장", "ok"],
  warn: ["확인 필요", "caution"],
  need_vehicle: ["차량 선택", "warn"],
  error: ["저장 불가", "danger"],
  cancel: ["취소 짝", "neutral"],
};
const w = (n: number | null) => (n == null ? "-" : won(n));
const toB64 = (f: File) =>
  new Promise<string>((ok, ng) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] ?? "");
    r.onerror = () => ng(new Error("파일을 읽지 못했습니다"));
    r.readAsDataURL(f);
  });

export default function FuelImport({ onDone, onClose }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [b64, setB64] = useState("");
  const [prev, setPrev] = useState<FuelImportPreview | null>(null);
  const [vmap, setVmap] = useState<Record<string, number>>({});
  const [over, setOver] = useState<Record<number, boolean>>({});
  const [onlyIssue, setOnlyIssue] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function preview(name: string, content: string, map: Record<string, number>) {
    setBusy(true);
    setError("");
    try {
      setPrev(await fuel.previewFuelImport({ file_name: name, content_b64: content, vehicle_map: map }));
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function readFile() {
    if (!file) return setError("파일을 선택하세요");
    if (file.size > MAX_BYTES) return setError("파일이 너무 큽니다 (2MB 이하)");
    setPrev(null);
    setVmap({});
    setOver({});
    try {
      const content = await toB64(file);
      setB64(content);
      await preview(file.name, content, {});
    } catch (e) {
      setError(errText(e));
    }
  }

  // 끝번호 단위 차량 지정 → 서버가 다시 판정 (사용자가 바꾼 체크는 유지)
  function pickVehicle(code: string, id: string) {
    if (!file || !b64) return;
    const next = { ...vmap };
    if (id) next[code] = Number(id);
    else delete next[code];
    setVmap(next);
    void preview(file.name, b64, next);
  }

  const isOn = (r: FuelImportRow) => r.selectable && (over[r.row] ?? r.checked);
  const rows = prev?.rows ?? [];
  const vehicles = prev?.vehicles ?? [];
  const counts = prev?.counts ?? {};
  const picked = rows.filter(isOn);
  const pTotal = picked.reduce((s, r) => s + (r.total_amount ?? 0), 0);
  const pCost = picked.reduce((s, r) => s + (r.cost ?? 0), 0);
  const shown = onlyIssue ? rows.filter((r) => r.level !== "ok") : rows;

  async function save() {
    if (!file || !prev) return;
    if (!picked.length) return setError("저장할 행을 선택하세요");
    const msg = `${num(picked.length)}건 · 합계 ${won(pTotal)} · 물류비 반영 ${won(pCost)}을 저장할까요?\n`
      + "한 건이라도 문제가 있으면 아무것도 저장되지 않습니다. 저장 후 '엑셀 업로드 기록'에서 한 번에 되돌릴 수 있습니다.";
    if (!window.confirm(msg)) return;
    setBusy(true);
    setError("");
    try {
      await fuel.commitFuelImport({ file_name: file.name, content_b64: b64, vehicle_map: vmap, rows: picked.map((r) => r.row) });
      const first = picked.map((r) => r.date).filter((d): d is string => !!d).sort()[0];
      await onDone(first ? first.slice(0, 7) : null);
      onClose();
    } catch (e) {
      setError(errText(e));
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      size="xl"
      title="주유 거래내역 엑셀 업로드"
      onClose={onClose}
      footer={
        <>
          {prev && (
            <span className="muted small grow">
              선택 {num(picked.length)}건 · 합계 {won(pTotal)} · 물류비 반영 {won(pCost)}
            </span>
          )}
          <Button onClick={onClose}>닫기</Button>
          <Button variant="primary" disabled={busy || !picked.length} onClick={save}>
            {busy && prev ? "처리 중…" : `${num(picked.length)}건 저장`}
          </Button>
        </>
      }
    >
      {error && <div className="stack"><ErrorBox message={error} /></div>}
      <div className="form-grid">
        <label className="field field-wide">주유소 거래내역 파일 (.xls · .xlsx)
          <input type="file" className="input" accept=".xls,.xlsx"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPrev(null); setB64(""); }} />
        </label>
        <div className="form-actions">
          <Button variant="primary" disabled={busy || !file} onClick={readFile}>
            {busy && !prev ? "읽는 중…" : "미리보기"}
          </Button>
        </div>
      </div>
      <p className="muted small">
        머리글(일자·차량·합계)을 찾아 읽고, 차량별 합계·총 합계 줄은 저장하지 않고 검산에만 씁니다.
        차량 끝 4자리가 한 대에만 맞으면 자동 연결, 없거나 여러 대면 아래 표에서 차량을 선택하세요.
        중복 의심·연료 불일치 행은 체크가 해제된 채로 보여 주며, 저장할 때 서버가 다시 판정합니다.
      </p>

      {busy && !prev && <Spinner />}
      {prev && (
        <>
          <div className="kv-line mt">
            <Chip>{prev.file_kind.toUpperCase()} · 머리글 {prev.header_row}행 · 합계 줄 {num(prev.skipped)}개 제외</Chip>
            {LEVELS.filter((k) => counts[k]).map((k) => (
              <Chip key={k} tone={LEVEL[k][1]}>{LEVEL[k][0]} {num(counts[k])}</Chip>
            ))}
          </div>
          {prev.checks.map((c) => (
            <p key={c.text} className="small">
              <Chip tone={c.level === "ok" ? "ok" : "caution"}>{c.level === "ok" ? "검산 일치" : "확인"}</Chip> {c.text}
            </p>
          ))}

          <p className="small mt"><b>차량 끝번호별 연결</b></p>
          <DataTable columns={["끝번호", { label: "행", num: true }, { label: "합계", num: true }, "연결", "차량"]}>
            {prev.codes.map((c) => {
              const cand = new Set(c.candidates);
              const cur = vmap[c.code] ?? (c.auto && c.vehicle_id != null ? c.vehicle_id : "");
              const opts = [...vehicles].sort((a, b) => Number(cand.has(b.id)) - Number(cand.has(a.id)));
              return (
                <tr key={c.code}>
                  <td>{c.code}</td>
                  <td className="num">{num(c.rows)}행</td>
                  <td className="num">{won(c.total)}</td>
                  <td>
                    {vmap[c.code] != null ? <Chip tone="internal">직접 선택</Chip>
                      : c.auto ? <Chip tone="ok">자동</Chip>
                      : <Chip tone="warn">{c.candidates.length ? `후보 ${c.candidates.length}대` : "맞는 차량 없음"}</Chip>}
                  </td>
                  <td>
                    <select className="input input-sm" value={String(cur)} disabled={busy}
                      onChange={(e) => pickVehicle(c.code, e.target.value)}>
                      <option value="">{c.auto ? "자동 연결 사용" : "차량 선택"}</option>
                      {opts.map((v) => (
                        <option key={v.id} value={v.id}>
                          {cand.has(v.id) ? "★ " : ""}{v.plate_no} · {FUEL_LABEL[v.fuel_type]}{v.active ? "" : " (미사용)"}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            })}
          </DataTable>

          <div className="row-gap mt">
            <label className="small">
              <input type="checkbox" checked={onlyIssue} onChange={(e) => setOnlyIssue(e.target.checked)} /> 확인이 필요한 행만 보기
            </label>
          </div>
          <div className="imp-tbl mt">
            <DataTable columns={["", "행", "차량", "일자", "제품", { label: "수량", num: true }, { label: "합계", num: true },
              { label: "공급가액", num: true }, { label: "부가세", num: true }, { label: "물류비 반영", num: true }, "판정"]}>
              {shown.map((r) => (
                <tr key={r.row} className={r.selectable ? undefined : "off"}>
                  <td className="c-chk">
                    <input type="checkbox" checked={isOn(r)} disabled={!r.selectable || busy}
                      onChange={(e) => setOver((o) => ({ ...o, [r.row]: e.target.checked }))} />
                  </td>
                  <td className="num">{r.row}</td>
                  <td>{r.plate_no ?? <span className="muted">{r.code}</span>}</td>
                  <td>{r.date ?? r.date_raw}</td>
                  <td>{r.product ?? ""}</td>
                  <td className="num">{r.quantity != null ? num(r.quantity) : "-"}</td>
                  <td className="num">{w(r.total_amount)}</td>
                  <td className="num">{w(r.supply_amount)}</td>
                  <td className="num">{w(r.vat_amount)}</td>
                  <td className="num">{w(r.cost)}</td>
                  <td className="small">
                    <Chip tone={LEVEL[r.level][1]}>{LEVEL[r.level][0]}</Chip>
                    {r.messages.map((m) => <div key={m} className="muted">{m}</div>)}
                  </td>
                </tr>
              ))}
            </DataTable>
          </div>
        </>
      )}
    </Modal>
  );
}
