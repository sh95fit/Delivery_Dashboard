import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import { addExclusion, addExtra, addHold, deleteExclusion, deleteExtra, releaseHold, setIncDelta, updateExtra } from "@/api/incentive";
import type { ExcludeReason, IncDayRow, IncDayView } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num } from "@/lib/format";
import { STATUS, parseAmt, wonOr } from "./util";

type Props = { row: IncDayRow; view: IncDayView; locked: boolean; onClose: () => void; onChanged: () => Promise<void> };
type ExForm = { aid: number; reason: ExcludeReason | ""; memo: string };
const BIG = 100_000;

export default function IncentiveDetailModal({ row, view, locked, onClose, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [ex, setEx] = useState<ExForm | null>(null);
  const [delta, setDelta] = useState(row.delta ? String(row.delta) : "");
  const [deltaReason, setDeltaReason] = useState(row.delta_info?.reason ?? "");
  const [holdReason, setHoldReason] = useState("");
  const [xf, setXf] = useState({ item: "", amount: "", memo: "" });
  const [edit, setEdit] = useState<{ id: number; amount: string; memo: string } | null>(null);

  const used = new Set(row.extra_list.map((x) => x.item_id));
  const xAmt = parseAmt(xf.amount);
  const eAmt = edit ? parseAmt(edit.amount) : null;
  const pending = !!ex || !!edit || xf.item !== "" || xf.amount !== "" || holdReason.trim() !== ""
    || delta !== (row.delta ? String(row.delta) : "");

  function close() {
    if (pending && !confirm("저장하지 않은 입력이 있습니다. 닫을까요?")) return;
    onClose();
  }
  async function run(fn: () => Promise<unknown>, done: string): Promise<boolean> {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await fn();
      await onChanged();
      setMsg(`✓ ${done}`);
      return true;
    } catch (e) {
      setError(errText(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  /* ---- 배송지 제외 ---- */
  async function saveEx() {
    if (!ex || !ex.reason) return;
    const f = ex;
    if (await run(() => addExclusion({ work_date: view.date, manager_id: row.manager_id, address_id: f.aid,
      reason: f.reason as ExcludeReason, memo: f.memo.trim() || null }), "배송지 제외")) setEx(null);
  }
  async function undoEx(id: number, name: string) {
    if (!confirm(`'${name}' 제외를 해제할까요? (수량이 다시 집계됩니다)`)) return;
    await run(() => deleteExclusion(id), "제외 해제");
  }

  /* ---- ± 조정 ---- */
  async function saveDelta() {
    const t = delta.trim() === "" ? "0" : delta.trim();
    if (!/^[-+]?\d{1,4}$/.test(t)) { setError("± 조정은 정수로 입력하세요 (예: -3)"); return; }
    const v = Number(t);
    if (v !== 0 && !deltaReason.trim()) { setError("± 조정은 사유를 입력하세요 (예: 퀵으로 일부 3개 발송)"); return; }
    if (await run(() => setIncDelta(view.date, row.manager_id, v, v ? deltaReason.trim() : null),
      v ? `제품 수 ${v > 0 ? "+" : ""}${v} 조정` : "조정 지움")) {
      setDelta(v ? String(v) : "");
      if (!v) setDeltaReason("");
    }
  }

  /* ---- 미지급 ---- */
  async function hold() {
    const r = holdReason.trim();
    if (!r) return;
    if (!confirm(`${row.manager_name} · ${view.date} 데일리 인센티브를 미지급 처리할까요?\n사유: ${r}\n(특수 수당은 그대로 지급)`)) return;
    if (await run(() => addHold(view.date, row.manager_id, r), "미지급 등록")) setHoldReason("");
  }
  async function release(id: number) {
    const r = prompt("미지급 해제 사유를 입력하세요")?.trim();
    if (!r) return;
    await run(() => releaseHold(id, r), "미지급 해제");
  }

  /* ---- 특수 수당 ---- */
  async function addX() {
    const item = view.extra_items.find((i) => String(i.id) === xf.item);
    if (!item || xAmt == null) return;
    const big = xAmt >= BIG ? `\n\n⚠ ${num(BIG)}원 이상입니다. 금액을 다시 확인하세요.` : "";
    if (!confirm(`${row.manager_name} · ${view.date}\n${item.name} ${num(xAmt)}원${xf.memo.trim() ? ` (${xf.memo.trim()})` : ""}\n\n특수 수당으로 추가할까요?${big}`)) return;
    if (await run(() => addExtra({ work_date: view.date, manager_id: row.manager_id, item_id: item.id, qty: 1,
      unit_amount: xAmt, memo: xf.memo.trim() || null }), `${item.name} ${num(xAmt)}원 추가`)) {
      setXf({ item: "", amount: "", memo: "" });
    }
  }
  async function saveEdit() {
    if (!edit || eAmt == null) return;
    const e = edit;
    const old = row.extra_list.find((x) => x.id === e.id);
    if (!confirm(`${old?.item_name ?? "특수 수당"} 금액을 ${num(old?.amount)}원 → ${num(eAmt)}원으로 수정할까요?`
      + (eAmt >= BIG ? `\n\n⚠ ${num(BIG)}원 이상입니다.` : ""))) return;
    if (await run(() => updateExtra(e.id, { qty: 1, unit_amount: eAmt, memo: e.memo.trim() || null }), "특수 수당 수정")) setEdit(null);
  }
  async function removeX(id: number, name: string) {
    const r = prompt(`'${name}' 특수 수당 삭제 사유를 입력하세요`)?.trim();
    if (!r) return;
    await run(() => deleteExtra(id, r), "특수 수당 삭제");
  }

  const reasons = Object.entries(view.exclude_reasons) as Array<[ExcludeReason, string]>;

  return (
    <Modal open size="xl" title={`${row.manager_name} · ${view.date} 인센티브 상세`} onClose={close}
      footer={<Button onClick={close}>닫기</Button>}>
      {locked && <div className="wl-block">{view.closed ? "마감된 달입니다" : view.future ? "미래 날짜입니다" : "관리자만 수정할 수 있습니다"} — 조회만 가능</div>}
      {error && <ErrorBox message={error} />}
      {msg && <div className="notice">{msg}</div>}

      <div className="inc-calc">
        <div>
          제품 수 = 자동 {num(row.auto_qty)} (가정식 {num(row.gajung_qty)} + 밀 {num(row.mil_qty)})
          {row.excluded_qty ? ` − 제외 ${num(row.excluded_qty)}` : ""}
          {row.delta ? ` ${row.delta > 0 ? "+" : "−"} 조정 ${num(Math.abs(row.delta))}` : ""}
          {" = "}<b>{num(row.product_total)}</b> → {wonOr(row.product_incentive)}
          {row.product_unit ? ` (초과분 × ${num(row.product_unit)}원)` : ""}
        </div>
        <div>
          고객사 수 = {row.accounts == null ? <Chip tone="caution">입력 필요 (일자 표에서 입력)</Chip> : <b>{num(row.accounts)}</b>}
          {" → "}{wonOr(row.account_incentive)}{row.account_unit ? ` (초과분 × ${num(row.account_unit)}원)` : ""}
          <span className="inc-ref"> · 참고: 배송지 {num(row.stops)} · 주문 고객사 {num(row.order_accounts)}</span>
        </div>
        <div className="inc-ref">참고(집계 제외): 석식 {num(row.dinner_qty)} · 파일럿 가정식 {num(row.pilot_qty)}</div>
        <div className="inc-calc-sum">
          데일리 인센티브 {row.held ? <><s>{wonOr(row.incentive)}</s> → 0원 (미지급)</> : wonOr(row.payable)}
          {" + "}특수 수당 {num(row.extras)}원 = <b>{num(row.total)}원</b>{" "}
          <Chip tone={STATUS[row.status][1]}>{STATUS[row.status][0]}</Chip>
        </div>
        {row.warns.map((w) => <div key={w} className="wl-warn">⚠ {w}</div>)}
      </div>

      <section className="inc-sec">
        <h3>① 배송지별 수량 · 제외</h3>
        <p className="hint">퀵 발송·다른 매니저 처리·미배송처럼 이 매니저가 처리하지 않은 배송지는 [제외]하세요. 그 배송지의 가정식·밀 수량이 전부 빠집니다.</p>
        <table className="tbl inc-mini">
          <thead><tr><th>배송지</th><th className="num">가정식</th><th className="num">밀</th>
            <th className="num">석식·파일럿</th><th className="num">주문 고객사</th><th>상태</th><th /></tr></thead>
          <tbody>
            {row.stop_list.map((s) => {
              const x = s.exclusion;
              const name = s.address_name ?? `배송지 ${s.address_id}`;
              return (
                <tr key={s.address_id} className={x ? "excluded" : undefined}>
                  <td>{name}{s.shared && !x && <Chip tone="caution" title="같은 날 다른 계정에도 배정됨">함께 배정</Chip>}</td>
                  <td className="num">{num(s.gajung_qty)}</td>
                  <td className="num">{num(s.mil_qty)}</td>
                  <td className="num inc-ref">{num(s.dinner_qty)} · {num(s.pilot_qty)}</td>
                  <td className="num">{num(s.order_accounts)}</td>
                  <td className="keep">
                    {x ? <Chip tone="warn" title={`${x.created_by ?? ""} ${x.memo ?? ""}`}>제외 · {x.reason_label}</Chip>
                      : ex?.aid === s.address_id ? (
                        <span className="inc-row">
                          <select className="input input-sm" value={ex.reason}
                            onChange={(e) => setEx({ ...ex, reason: e.target.value as ExcludeReason | "" })}>
                            <option value="">사유 선택</option>
                            {reasons.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                          </select>
                          <input className="input input-sm" placeholder="메모 (선택)" maxLength={200} value={ex.memo}
                            onChange={(e) => setEx({ ...ex, memo: e.target.value })} />
                        </span>
                      ) : "집계"}
                  </td>
                  <td className="keep">
                    {locked ? null : x ? (
                      <Button size="sm" disabled={busy} onClick={() => undoEx(x.id, name)}>제외 해제</Button>
                    ) : ex?.aid === s.address_id ? (
                      <span className="inc-row">
                        <Button size="sm" variant="primary" disabled={busy || !ex.reason} onClick={saveEx}>제외 저장</Button>
                        <Button size="sm" variant="ghost" onClick={() => setEx(null)}>취소</Button>
                      </span>
                    ) : (
                      <Button size="sm" disabled={busy || !!ex} onClick={() => setEx({ aid: s.address_id, reason: "", memo: "" })}>제외</Button>
                    )}
                  </td>
                </tr>
              );
            })}
            {row.stop_list.length === 0 && <tr><td colSpan={7} className="muted small">배정된 배송지가 없습니다.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="inc-sec">
        <h3>② 제품 수 ± 조정 (일부만 빠지는 경우)</h3>
        <p className="hint">배송지 하나가 통째로 빠지면 ①의 제외를 쓰세요. 일부 수량만 다를 때만 씁니다. 0 또는 빈칸으로 저장하면 조정이 지워집니다.</p>
        <div className="inc-row">
          <input className="input input-sm inc-band-in" inputMode="numeric" placeholder="예: -3" value={delta}
            disabled={locked} onChange={(e) => setDelta(e.target.value.trim())} />
          <input className="input input-sm" style={{ minWidth: 280 }} placeholder="사유 (필수, 예: 퀵으로 3개 발송)"
            maxLength={200} value={deltaReason} disabled={locked} onChange={(e) => setDeltaReason(e.target.value)} />
          {!locked && <Button size="sm" variant="primary" disabled={busy} onClick={saveDelta}>조정 저장</Button>}
          {row.delta_info && <span className="inc-ref">현재 {row.delta_info.value > 0 ? "+" : ""}{row.delta_info.value} · {row.delta_info.created_by}</span>}
        </div>
      </section>

      <section className="inc-sec">
        <h3>③ 미지급 (데일리 인센티브만)</h3>
        <p className="hint">과실이 1건이라도 남아 있으면 그날 제품·고객사 인센티브가 0원이 됩니다. 특수 수당에는 영향이 없습니다.</p>
        {row.hold_list.map((h) => (
          <div key={h.id} className="inc-row">
            <Chip tone="danger">미지급</Chip> {h.reason} <span className="inc-ref">{h.created_by}</span>
            {!locked && <Button size="sm" disabled={busy} onClick={() => release(h.id)}>해제</Button>}
          </div>
        ))}
        {!locked && (
          <div className="inc-row mt">
            <input className="input input-sm" style={{ minWidth: 320 }} placeholder="과실 사유 (필수, 예: 배송 지연 30분)"
              maxLength={200} value={holdReason} onChange={(e) => setHoldReason(e.target.value)} />
            <Button size="sm" variant="danger" disabled={busy || !holdReason.trim()} onClick={hold}>미지급 등록</Button>
          </div>
        )}
      </section>

      <section className="inc-sec">
        <h3>④ 특수 수당 (인센티브와 별도 · 추가 지급)</h3>
        <p className="hint">품목을 고르고 금액을 그때그때 입력합니다. 같은 날 같은 품목은 1줄만 둘 수 있습니다 (추가분은 금액을 수정하세요).</p>
        {row.extra_list.length > 0 && (
          <table className="tbl inc-mini">
            <thead><tr><th>품목</th><th className="num">금액</th><th>비고</th><th>입력</th><th /></tr></thead>
            <tbody>
              {row.extra_list.map((x) => edit?.id === x.id ? (
                <tr key={x.id}>
                  <td>{x.item_name}</td>
                  <td className="num">
                    <input className="input input-sm inc-band-in" inputMode="numeric" value={edit.amount}
                      onChange={(e) => setEdit({ ...edit, amount: e.target.value })} />
                    <div className="inc-amt-preview">{eAmt == null ? "금액 확인" : `= ${num(eAmt)}원`}</div>
                  </td>
                  <td><input className="input input-sm" maxLength={200} value={edit.memo}
                    onChange={(e) => setEdit({ ...edit, memo: e.target.value })} /></td>
                  <td />
                  <td className="inc-row">
                    <Button size="sm" variant="primary" disabled={busy || eAmt == null} onClick={saveEdit}>저장</Button>
                    <Button size="sm" variant="ghost" onClick={() => setEdit(null)}>취소</Button>
                  </td>
                </tr>
              ) : (
                <tr key={x.id}>
                  <td>{x.item_name}</td>
                  <td className="num"><b>{num(x.amount)}</b></td>
                  <td>{x.memo ?? ""}</td>
                  <td className="inc-ref">{x.created_by}</td>
                  <td className="inc-row">
                    {!locked && <>
                      <Button size="sm" disabled={busy || !!edit}
                        onClick={() => setEdit({ id: x.id, amount: String(x.amount), memo: x.memo ?? "" })}>수정</Button>
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => removeX(x.id, x.item_name)}>삭제</Button>
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!locked && (
          <div className="inc-row mt">
            <select className="input input-sm" value={xf.item} onChange={(e) => setXf({ ...xf, item: e.target.value })}>
              <option value="">품목 선택</option>
              {view.extra_items.map((i) => (
                <option key={i.id} value={i.id} disabled={used.has(i.id)}>
                  {i.name}{used.has(i.id) ? " (등록됨 — 위에서 수정)" : ""}
                </option>
              ))}
            </select>
            <span>
              <input className="input input-sm inc-band-in" inputMode="numeric" placeholder="금액 (원)" value={xf.amount}
                onChange={(e) => setXf({ ...xf, amount: e.target.value })} />
              <div className="inc-amt-preview">{xf.amount === "" ? "" : xAmt == null ? "1원~100만 원 숫자" : `= ${num(xAmt)}원`}</div>
            </span>
            <input className="input input-sm" style={{ minWidth: 220 }} placeholder="비고 (선택, 예: 2곳 수거)"
              maxLength={200} value={xf.memo} onChange={(e) => setXf({ ...xf, memo: e.target.value })} />
            <Button size="sm" variant="primary" disabled={busy || !xf.item || xAmt == null} onClick={addX}>특수 수당 추가</Button>
          </div>
        )}
        {view.extra_items.length === 0 && <div className="muted small">사용 중인 품목이 없습니다 (단가표·품목 탭에서 추가)</div>}
      </section>
    </Modal>
  );
}
