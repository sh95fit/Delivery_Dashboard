import { useEffect, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import Modal from "@/components/ui/Modal";
import Spinner from "@/components/ui/Spinner";
import { deleteRates, getExtraItems, getRates, saveExtraItem, saveRates } from "@/api/incentive";
import type { Band, BandKind, ExtraItem, RateSet } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import { bandText } from "./util";

type Row = { end: string; amount: string };
const KIND: Record<BandKind, string> = { product: "제품 수 (개당)", account: "고객사 수 (곳당)" };
const toRows = (bs: Band[]): Row[] => bs.map((b) => ({ end: b.end == null ? "" : String(b.end), amount: String(b.amount) }));
function toBands(rows: Row[]): Band[] {
  let start = 0;
  return rows.map((r) => {
    const b = { start, end: r.end.trim() === "" ? null : Number(r.end), amount: Number(r.amount || 0) };
    start = b.end ?? start;
    return b;
  });
}

function BandEditor({ kind, rows, onChange }: { kind: BandKind; rows: Row[]; onChange: (r: Row[]) => void }) {
  const bands = toBands(rows);
  const set = (i: number, p: Partial<Row>) => onChange(rows.map((r, k) => (k === i ? { ...r, ...p } : r)));
  return (
    <div>
      <h3 className="small">{KIND[kind]}</h3>
      <table className="tbl inc-mini">
        <thead><tr><th>초과</th><th>이하 (끝)</th><th>단가(원)</th><th /></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="num">{num(bands[i].start)}</td>
              <td><input className="input input-sm inc-band-in" inputMode="numeric" value={r.end}
                placeholder={i === rows.length - 1 ? "비우면 끝 없음" : "끝값"}
                onChange={(e) => set(i, { end: e.target.value.replace(/\D/g, "") })} /></td>
              <td><input className="input input-sm inc-band-in" inputMode="numeric" value={r.amount}
                onChange={(e) => set(i, { amount: e.target.value.replace(/\D/g, "") })} /></td>
              <td>{rows.length > 1 && <Button size="sm" variant="ghost" onClick={() => onChange(rows.filter((_, k) => k !== i))}>삭제</Button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="sm" onClick={() => onChange([...rows, { end: "", amount: "" }])}>구간 추가</Button>
    </div>
  );
}

function RateEditor({ base, onClose, onSaved }: { base: { id: number | null; set: RateSet | null }; onClose: () => void; onSaved: () => void }) {
  const [from, setFrom] = useState(base.id == null ? todayKst() : base.set?.effective_from ?? todayKst());
  const [memo, setMemo] = useState(base.id == null ? "" : base.set?.memo ?? "");
  const [prod, setProd] = useState<Row[]>(toRows(base.set?.bands.product ?? [{ start: 0, end: null, amount: 0 }]));
  const [acc, setAcc] = useState<Row[]>(toRows(base.set?.bands.account ?? [{ start: 0, end: null, amount: 0 }]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    setBusy(true);
    try {
      await saveRates(base.id, { effective_from: from, memo: memo.trim() || null, product: toBands(prod), account: toBands(acc) });
      onSaved();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open size="lg" title={base.id == null ? "새 단가표 추가" : "단가표 수정"} onClose={onClose}
      footer={<><Button onClick={onClose}>취소</Button><Button variant="primary" disabled={busy || !from} onClick={save}>{busy ? "저장 중…" : "저장"}</Button></>}>
      {error && <ErrorBox message={error} />}
      <p className="muted small">
        {base.id == null ? "적용 시작일부터 새 단가가 적용되고, 그 전 날짜는 기존 단가로 계산됩니다." : "입력 오류 보완용입니다. 실제 단가 변경은 '새 단가표 추가'로 하세요."}
        {" "}초과 기준 = 단가가 0보다 큰 첫 구간의 시작값. 마지막 구간 끝값을 비우면 그 이상 전부입니다.
      </p>
      <div className="inc-row">
        <label>적용 시작일 <input type="date" className="input input-sm" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <input className="input input-sm" style={{ minWidth: 260 }} placeholder="메모 (선택)" maxLength={200} value={memo} onChange={(e) => setMemo(e.target.value)} />
      </div>
      <div className="inc-bands mt">
        <BandEditor kind="product" rows={prod} onChange={setProd} />
        <BandEditor kind="account" rows={acc} onChange={setAcc} />
      </div>
    </Modal>
  );
}

export default function IncentiveRatesTab({ isAdmin }: { isAdmin: boolean }) {
  const [sets, setSets] = useState<RateSet[]>([]);
  const [items, setItems] = useState<ExtraItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<{ id: number | null; set: RateSet | null } | null>(null);
  const [newItem, setNewItem] = useState("");

  async function load() {
    try {
      const [r, i] = await Promise.all([getRates(), getExtraItems()]);
      setSets(r.items);
      setItems(i.items);
      setError("");
    } catch (e) {
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);
  const current = sets.find((s) => s.current) ?? null;

  async function remove(s: RateSet) {
    if (!confirm(`${s.effective_from} 단가표를 삭제할까요? (그 기간은 이전 단가표로 계산됩니다)`)) return;
    try { await deleteRates(s.id); await load(); } catch (e) { setError(errText(e)); }
  }
  async function toggle(i: ExtraItem) {
    try {
      await saveExtraItem(i.id, { name: i.name, unit_amount: null, active: !i.active, sort_order: i.sort_order, memo: i.memo });
      await load();
    } catch (e) { setError(errText(e)); }
  }
  async function addItem() {
    const name = newItem.trim();
    if (!name) return;
    try {
      await saveExtraItem(null, { name, unit_amount: null, active: true,
        sort_order: Math.max(0, ...items.map((x) => x.sort_order)) + 1, memo: null });
      setNewItem("");
      await load();
    } catch (e) { setError(errText(e)); }
  }

  if (loading) return <Spinner />;
  return (
    <>
      {error && <ErrorBox message={error} />}
      <Panel title="인센티브 단가표"
        right={isAdmin && <Button size="sm" variant="primary" onClick={() => setEditing({ id: null, set: current })}>새 단가표 추가</Button>}
        desc="인센티브 = (수량 − 초과 기준) × 수량이 들어간 구간 단가. 마지막 구간 끝값이 있는데 수량이 넘으면 최대 구간 단가를 적용하고 경고를 표시합니다.">
        <div className="inc-rates">
          {sets.map((s) => (
            <div key={s.id} className={`inc-card${s.current ? " current" : ""}`}>
              <div className="inc-card-h">
                <span><b>{s.effective_from}</b>부터 {s.current && <Chip tone="ok">현재 적용</Chip>}
                  {s.memo && <span className="inc-ref"> · {s.memo}</span>}</span>
                {isAdmin && <span className="inc-row">
                  <Button size="sm" onClick={() => setEditing({ id: s.id, set: s })}>수정</Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(s)}>삭제</Button>
                </span>}
              </div>
              <div className="inc-bands">
                {(["product", "account"] as BandKind[]).map((k) => (
                  <table key={k} className="tbl inc-mini">
                    <thead><tr><th>{KIND[k]}</th><th className="num">단가</th></tr></thead>
                    <tbody>{s.bands[k].map((b) => <tr key={b.start}><td>{bandText(b)}</td><td className="num">{num(b.amount)}</td></tr>)}</tbody>
                  </table>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="특수 수당 품목" desc="금액은 지급할 때마다 입력합니다 (품목에 고정 금액 없음). 쓰지 않는 품목은 '사용 안 함'으로 두면 이력은 유지되고 선택 목록에서만 빠집니다.">
        <table className="tbl inc-mini">
          <thead><tr><th>품목</th><th>상태</th><th /></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} className={i.active ? undefined : "off"}>
                <td>{i.name}</td>
                <td>{i.active ? <Chip tone="ok">사용</Chip> : <Chip>사용 안 함</Chip>}</td>
                <td>{isAdmin && <Button size="sm" onClick={() => toggle(i)}>{i.active ? "사용 안 함" : "다시 사용"}</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {isAdmin && (
          <div className="inc-row mt">
            <input className="input input-sm" placeholder="새 품목 이름 (예: 오전 추가 배송)" maxLength={50} value={newItem}
              onChange={(e) => setNewItem(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addItem(); }} />
            <Button size="sm" disabled={!newItem.trim()} onClick={addItem}>품목 추가</Button>
          </div>
        )}
      </Panel>
      {editing && <RateEditor base={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </>
  );
}
