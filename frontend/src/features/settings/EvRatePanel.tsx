import { useCallback, useEffect, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Modal from "@/components/ui/Modal";
import * as fuel from "@/api/fuel";
import { EV_SPEED_LABEL } from "@/api/fuel";
import type { EvRate, EvRatePreview, EvRateSet, EvSettings, EvSpeed } from "@/api/fuel";
import { errText } from "@/lib/form";
import { kstDateTime } from "@/lib/format";

/* S3-P2g-1 전기차 충전 단가 — 로밍 요금 매트릭스(기후에너지환경부 카드 행) 업로드 · 예상 충전비 기준 설정 */

type Props = { isAdmin: boolean };

const SPEEDS: EvSpeed[] = ["fast", "ultra", "slow"];
const MAX_BYTES = 2 * 1024 * 1024;
const price = (p: number) => p.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
const toB64 = (f: File) =>
  new Promise<string>((ok, ng) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] ?? "");
    r.onerror = () => ng(new Error("파일을 읽지 못했습니다"));
    r.readAsDataURL(f);
  });

export default function EvRatePanel({ isAdmin }: Props) {
  const [sets, setSets] = useState<EvRateSet[] | null>(null);
  const [cfg, setCfg] = useState<EvSettings | null>(null);
  const [speedIn, setSpeedIn] = useState<EvSpeed>("fast");
  const [kmIn, setKmIn] = useState("3.1");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [b64, setB64] = useState("");
  const [prev, setPrev] = useState<EvRatePreview | null>(null);
  const [speed, setSpeed] = useState<EvSpeed | "">("");
  const [eff, setEff] = useState("");
  const [memo, setMemo] = useState("");
  const [view, setView] = useState<{ set: EvRateSet; rates: EvRate[] } | null>(null);

  const load = useCallback(async () => {
    const r = await fuel.listEvRates();
    setSets(r.sets);
    setCfg(r.settings);
    setSpeedIn(r.settings.ev_speed);
    setKmIn(String(r.settings.ev_km_per_kwh));
  }, []);

  useEffect(() => {
    load().catch((e) => setError(errText(e)));
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try { await fn(); await load(); return true; } catch (e) { setError(errText(e)); return false; } finally { setBusy(false); }
  }

  function saveSettings() {
    const km = Number(kmIn);
    if (!(km > 0 && km <= 20)) return setError("기본 전비는 0보다 크고 20 이하로 입력하세요 (km/kWh)");
    void run(() => fuel.saveEvSettings({ ev_speed: speedIn, ev_km_per_kwh: km }));
  }

  function openUpload() {
    setError("");
    setFile(null);
    setB64("");
    setPrev(null);
    setSpeed("");
    setEff("");
    setMemo("");
    setOpen(true);
  }

  async function readFile() {
    if (!file) return setError("파일을 선택하세요");
    if (file.size > MAX_BYTES) return setError("파일이 너무 큽니다 (2MB 이하)");
    setBusy(true);
    setError("");
    setPrev(null);
    try {
      const content = await toB64(file);
      const p = await fuel.previewEvRates({ file_name: file.name, content_b64: content });
      setB64(content);
      setPrev(p);
      setSpeed(p.speed ?? "");
      setEff(p.effective_from ?? "");
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!file || !prev || !b64) return;
    if (!speed) return setError("충전 속도를 선택하세요");
    if (!eff) return setError("적용 시작일을 입력하세요");
    const sp: EvSpeed = speed;
    const body = { file_name: file.name, content_b64: b64, speed: sp, effective_from: eff, memo: memo.trim() || null };
    const ok = await run(() => fuel.commitEvRates(body));
    if (ok) setOpen(false);
  }

  function remove(s: EvRateSet) {
    const msg = `${EV_SPEED_LABEL[s.speed]} ${s.effective_from} 단가(사업자 ${s.rate_count}곳)를 삭제할까요?\n`
      + "물류비 참고 칸의 전기차 예상 충전비가 남은 단가로 다시 계산됩니다.";
    if (!window.confirm(msg)) return;
    void run(() => fuel.deleteEvRates(s.id));
  }

  async function show(s: EvRateSet) {
    setError("");
    try {
      setView({ set: s, rates: await fuel.getEvRates(s.id) });
    } catch (e) {
      setError(errText(e));
    }
  }

  const has = (sp: EvSpeed) => (sets ?? []).some((s) => s.speed === sp);

  return (
    <>
      <Panel
        title="전기차 충전 단가 (예상 충전비 기준)"
        right={isAdmin ? <Button size="sm" disabled={busy} onClick={openUpload}>요금 매트릭스 업로드</Button> : undefined}
      >
        {error && !open && <div className="stack"><ErrorBox message={error} /></div>}
        <p className="muted small">
          예상 충전비 = 주행거리 ÷ 전비(차량 연비 칸, 없으면 기본 전비) × 기후에너지환경부 카드로 기후에너지환경부 충전기를 쓸 때 단가.
          물류비 화면의 NCP 예상·오피넷 기준 참고 칸에 같은 값으로 표시하고, 물류비 합계에는 넣지 않습니다.
          실제 비용은 법인카드 결제금액을 주유 기록(전기 차량)으로 입력하면 됩니다.
        </p>
        {cfg && (
          <div className="row-gap">
            <span className="small">예상 기준</span>
            <select className="input" value={speedIn} disabled={!isAdmin || busy}
              onChange={(e) => setSpeedIn(e.target.value as EvSpeed)}>
              {SPEEDS.map((s) => <option key={s} value={s}>{EV_SPEED_LABEL[s]}</option>)}
            </select>
            <span className="small">기본 전비</span>
            <input className="input input-sm" inputMode="decimal" value={kmIn} disabled={!isAdmin || busy}
              onChange={(e) => setKmIn(e.target.value)} />
            <span className="small">km/kWh</span>
            {isAdmin && <Button size="sm" variant="primary" disabled={busy} onClick={saveSettings}>저장</Button>}
            {sets && !has(cfg.ev_speed) && (
              <Chip tone="warn">{EV_SPEED_LABEL[cfg.ev_speed]} 단가 없음 · 다른 속도 단가로 대신 계산</Chip>
            )}
          </div>
        )}
        {!sets ? (
          <p className="muted">불러오는 중…</p>
        ) : sets.length === 0 ? (
          <p className="muted mt">올린 요금 매트릭스가 없습니다. 무공해차 누리집에서 급속 로밍 요금 매트릭스를 내려받아 올리세요.</p>
        ) : (
          <div className="mt">
            <DataTable columns={["속도", "적용 시작일", { label: "기준 단가(원/kWh)", num: true }, { label: "사업자", num: true },
              "파일", "올린 사람", "관리"]}>
              {sets.map((s) => (
                <tr key={s.id}>
                  <td>
                    {EV_SPEED_LABEL[s.speed]}
                    {cfg?.ev_speed === s.speed ? <> <Chip tone="ok">예상 기준</Chip></> : null}
                  </td>
                  <td>{s.effective_from}</td>
                  <td className="num">{price(s.base_price)}</td>
                  <td className="num">{s.rate_count}곳</td>
                  <td>{s.file_name ?? "-"}{s.memo ? <span className="muted small"> · {s.memo}</span> : null}</td>
                  <td>{s.created_by ?? "-"} · {kstDateTime(s.created_at)}</td>
                  <td>
                    <div className="row-gap">
                      <Button size="sm" disabled={busy} onClick={() => void show(s)}>보기</Button>
                      {isAdmin && <Button size="sm" variant="danger" disabled={busy} onClick={() => remove(s)}>삭제</Button>}
                    </div>
                  </td>
                </tr>
              ))}
            </DataTable>
          </div>
        )}
      </Panel>

      <Modal
        open={isAdmin && open}
        title="로밍 요금 매트릭스 업로드"
        onClose={() => setOpen(false)}
        footer={
          <>
            {prev && (
              <span className="muted small grow">
                {prev.issuer} 카드 · 사업자 {prev.rate_count}곳 · 기준 {price(prev.base_price)}원/kWh
              </span>
            )}
            <Button onClick={() => setOpen(false)}>닫기</Button>
            <Button variant="primary" disabled={busy || !prev} onClick={commit}>저장</Button>
          </>
        }
      >
        {error && <div className="stack"><ErrorBox message={error} /></div>}
        <div className="form-grid">
          <label className="field field-wide">요금 매트릭스 파일 (.xlsx · .xls)
            <input type="file" className="input" accept=".xls,.xlsx"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPrev(null); setB64(""); }} />
          </label>
          <div className="form-actions">
            <Button variant="primary" disabled={busy || !file} onClick={readFile}>{busy && !prev ? "읽는 중…" : "미리보기"}</Button>
          </div>
        </div>
        {prev && (
          <>
            <div className="form-grid mt">
              <label className="field">충전 속도 *
                <select className="input" value={speed} onChange={(e) => setSpeed(e.target.value as EvSpeed | "")}>
                  <option value="">선택</option>
                  {SPEEDS.map((s) => <option key={s} value={s}>{EV_SPEED_LABEL[s]}</option>)}
                </select>
              </label>
              <label className="field">적용 시작일 *
                <input type="date" className="input" value={eff} onChange={(e) => setEff(e.target.value)} />
              </label>
              <label className="field field-wide">메모
                <input className="input" value={memo} maxLength={200} onChange={(e) => setMemo(e.target.value)} />
              </label>
            </div>
            <p className="muted small">
              속도·적용 시작일은 파일 이름에서 읽었습니다. 다르면 고친 뒤 저장하세요.
              머리글 {prev.header_row}행 · 단가 없는 칸('-') {prev.skipped}개 제외.
            </p>
            {prev.duplicate_id != null && (
              <p className="small">
                <Chip tone="warn">이미 있음</Chip> 같은 속도·적용 시작일 단가(#{prev.duplicate_id})가 있습니다 — 목록에서 삭제한 뒤 저장하세요
              </p>
            )}
            <div className="imp-tbl mt">
              <DataTable columns={["충전 사업자", { label: "원/kWh", num: true }]}>
                {prev.rates.map((r) => (
                  <tr key={r.operator}>
                    <td>{r.operator}{r.operator === prev.base_operator ? <> <Chip tone="ok">예상 기준</Chip></> : null}</td>
                    <td className="num">{price(r.price)}</td>
                  </tr>
                ))}
              </DataTable>
            </div>
          </>
        )}
      </Modal>

      <Modal
        open={view != null}
        title={view ? `${EV_SPEED_LABEL[view.set.speed]} · ${view.set.effective_from} 사업자별 단가 (${view.set.issuer} 카드)` : ""}
        onClose={() => setView(null)}
        footer={<Button onClick={() => setView(null)}>닫기</Button>}
      >
        {view && (
          <div className="imp-tbl">
            <DataTable columns={["충전 사업자", { label: "원/kWh", num: true }]}>
              {view.rates.map((r) => (
                <tr key={r.operator}>
                  <td>{r.operator}</td>
                  <td className="num">{price(r.price)}</td>
                </tr>
              ))}
            </DataTable>
          </div>
        )}
      </Modal>
    </>
  );
}
