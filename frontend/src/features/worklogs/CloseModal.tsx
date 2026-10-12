import { useEffect, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { closeMonth, getCloseCheck, hmm, reopenMonth } from "@/api/worklogs";
import type { CloseCheck, CloseTotals } from "@/api/worklogs";
import { errText } from "@/lib/form";
import { num, won } from "@/lib/format";

type Props = {
  month: string; isAdmin: boolean;
  onClose: () => void; onJump: (wid: number, day: number | null) => void; onChanged: (msg: string) => void;
  note?: string;   // 바로가기 입력 창에서 저장하고 돌아왔을 때 결과
};

const ts = (s: string | null) => (s ? new Date(s).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false }) : "-");
const totText = (t: CloseTotals | null) =>
  t ? `${num(t.people)}명 · ${num(t.days)}일 · 유급 ${hmm(t.paid_min)} · 근무표 지급 ${won(t.sheet_total)}` : "-";

/** 월 표 → 마감 점검 / 마감 / 해제 / 이력. [입력 바로가기] → 그 사람 입력 창 → 저장·닫기 후 이 창으로 돌아와 다시 점검 */
export default function CloseModal({ month, isAdmin, onClose, onJump, onChanged, note }: Props) {
  const [chk, setChk] = useState<CloseCheck | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [memo, setMemo] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [y, m] = month.split("-").map(Number);

  useEffect(() => {
    let alive = true;
    getCloseCheck(`${month}-01`)
      .then((v) => { if (alive) setChk(v); })
      .catch((e) => { if (alive) setError(errText(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [month]);

  const errs = chk?.issues.filter((i) => i.level === "error").length ?? 0;
  const warns = chk?.issues.filter((i) => i.level === "warn").length ?? 0;

  async function doClose() {
    if (!chk?.can_close) return;
    if (!confirm(`${y}년 ${m}월을 마감합니다.${warns ? `\n확인 항목 ${warns}건이 남아 있습니다.` : ""}\n` +
      "마감 후에는 이 달 근무·휴무 기록과, 이 달 말일 이전에 시작하는 계약·고정 계정 이력을 바꿀 수 없습니다.")) return;
    setBusy(true);
    setError("");
    try {
      const r = await closeMonth(`${month}-01`, memo.trim() || null);
      onChanged(`${y}년 ${m}월 마감 완료 (${totText(r.totals)})`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function doReopen() {
    const r = reason.trim();
    if (r.length < 2) { setError("해제 사유를 2자 이상 입력하세요"); return; }
    if (!confirm(`${y}년 ${m}월 마감을 해제합니다.\n사유: ${r}\n수정 후 다시 마감하세요.`)) return;
    setBusy(true);
    setError("");
    try {
      await reopenMonth(`${month}-01`, r);
      onChanged(`${y}년 ${m}월 마감 해제 (사유: ${r})`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open size="lg" onClose={onClose}
      title={<>{y}년 {m}월 마감 관리</>}
      footer={<>
        <Button onClick={onClose}>닫기</Button>
        {isAdmin && chk && !chk.closed && (
          <Button variant="primary" onClick={doClose} disabled={busy || !chk.can_close}>
            {busy ? "처리 중…" : chk.can_close ? `${m}월 마감` : `마감 불가 (차단 ${errs}건)`}
          </Button>
        )}
        {isAdmin && chk?.closed && (
          <Button variant="danger" onClick={doReopen} disabled={busy || reason.trim().length < 2}>
            {busy ? "처리 중…" : "마감 해제"}
          </Button>
        )}
      </>}
    >
      {error && <ErrorBox message={error} />}
      {note && <div className="notice">✓ {note}</div>}
      {loading ? <Spinner /> : chk && (
        <>
          <div className="cm-head">
            {chk.closed ? <Chip tone="ok">마감됨</Chip> : chk.ended ? <Chip tone="caution">마감 전</Chip> : <Chip>진행 중인 달</Chip>}
            <span className="small">현재 합계: <b>{totText(chk.totals)}</b></span>
            <span className="muted small">차단 {errs} · 확인 {warns}</span>
          </div>

          <div className="cm-title">점검 결과</div>
          {chk.issues.length === 0 ? (
            <div className="notice">✓ 점검 항목 없음{chk.closed ? "" : " — 마감할 수 있습니다"}</div>
          ) : (
            <div className="cm-wrap">
              <table className="tbl">
                <thead><tr><th>구분</th><th>이름</th><th>내용</th><th /></tr></thead>
                <tbody>
                  {chk.issues.map((i, k) => (
                    <tr key={k}>
                      <td>{i.level === "error" ? <Chip tone="danger">차단</Chip>
                        : i.level === "warn" ? <Chip tone="caution">확인</Chip> : <Chip>안내</Chip>}</td>
                      <td>{i.name ?? "-"}</td>
                      <td className="small">{i.msg}</td>
                      <td>{i.worker_id != null && (
                        <Button size="sm" variant="ghost" onClick={() => onJump(i.worker_id!, i.day)}
                          title={i.day ? `${i.day}일로 이동` : "한 달 입력 열기"}>
                          입력 바로가기
                        </Button>
                      )}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {isAdmin && !chk.closed && (
            <div className="cm-form">
              <input className="input input-sm" value={memo} maxLength={200} placeholder="마감 메모 (선택)"
                onChange={(e) => setMemo(e.target.value)} />
            </div>
          )}
          {isAdmin && chk.closed && (
            <div className="cm-form">
              <input className="input input-sm" value={reason} maxLength={200}
                placeholder="해제 사유 (필수, 예: 10/14 퇴근 오기 수정)" onChange={(e) => setReason(e.target.value)} />
            </div>
          )}

          <div className="cm-title">마감 이력</div>
          {chk.history.length === 0 ? <div className="muted small">이력 없음</div> : (
            <div className="cm-wrap">
              <table className="tbl">
                <thead><tr><th>마감</th><th>마감 시점 합계</th><th>해제</th><th>해제 사유</th></tr></thead>
                <tbody>
                  {chk.history.map((h) => (
                    <tr key={h.id}>
                      <td className="small">{ts(h.closed_at)}<br /><span className="muted">{h.closed_by}{h.memo ? ` · ${h.memo}` : ""}</span></td>
                      <td className="small">{totText(h.summary)}</td>
                      <td className="small">{h.reopened_at ? <>{ts(h.reopened_at)}<br /><span className="muted">{h.reopened_by}</span></> : <Chip tone="ok">유지 중</Chip>}</td>
                      <td className="small">{h.reopen_reason ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
