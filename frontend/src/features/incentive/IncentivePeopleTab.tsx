import { useEffect, useState } from "react";
import Panel from "@/components/ui/Panel";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { getIncPeople } from "@/api/incentive";
import type { IncPeopleView } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num } from "@/lib/format";

const TYPE: Record<string, string> = { employee: "근로소득", business: "사업자", freelancer: "프리랜서", regular: "정규직" };

type Props = { month: string; onMonth: (m: string) => void };

export default function IncentivePeopleTab({ month, onMonth }: Props) {
  const [view, setView] = useState<IncPeopleView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    getIncPeople(month).then((v) => { setView(v); setError(""); })
      .catch((e) => { setView(null); setError(errText(e)); })
      .finally(() => setLoading(false));
  }, [month]);

  const t = view?.totals;
  return (
    <Panel
      title={`${month} 담당자별 인센티브`}
      right={<input type="month" className="input input-sm" value={month}
        onChange={(e) => e.target.value && onMonth(e.target.value)} />}
      desc="계정 금액을 그날 담당한 사람에게 배정한 결과입니다 (담당 지정 → 근무 기록의 그날 계정 → 고정 계정 순). 정규직도 같은 기준으로 계산되며, 근무표에는 시급제·사업자·프리랜서만 들어갑니다."
    >
      {error && <ErrorBox message={error} />}
      {t && (
        <div className="muted small">
          합계 {num(t.total)}원 = 근무표 인센티브 칸 {num(t.on_sheet)} + 근무표 외(정규직 등) {num(t.off_sheet)}
          {t.unassigned > 0 && ` · 담당 미확인 ${num(t.unassigned)}원 (합계에서 빠짐)`}
        </div>
      )}
      {loading ? <Spinner /> : view && view.people.length === 0 && view.unassigned.length === 0 ? (
        <div className="muted small">이 달에 배정된 인센티브가 없습니다.</div>
      ) : view && (
        <>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>이름</th><th>구분</th><th>근무표</th><th className="num">배정 일수</th>
                  <th className="num">데일리 인센티브</th><th className="num">특수 수당</th>
                  <th className="num">합계</th><th className="num">고객사 수 미입력</th>
                </tr>
              </thead>
              <tbody>
                {view.people.map((p) => (
                  <tr key={p.worker_id}>
                    <td>{p.name} {!p.active && <Chip tone="caution">비활성</Chip>}</td>
                    <td>{p.pay_type === "monthly" ? "정규직" : TYPE[p.income_type ?? ""] ?? "-"}</td>
                    <td>{p.on_sheet ? <Chip tone="ok">인센티브 칸</Chip> : <Chip tone="warn">근무표 외 · 별도 지급</Chip>}</td>
                    <td className="num">{num(p.days)}{p.chosen_days ? <> <Chip tone="internal">지정 {p.chosen_days}일</Chip></> : null}</td>
                    <td className="num">{num(p.incentive)}</td>
                    <td className="num">{num(p.extras)}</td>
                    <td className="num"><b>{num(p.total)}</b></td>
                    <td className="num">{p.pending_days ? <Chip tone="warn">{p.pending_days}일</Chip> : "-"}</td>
                  </tr>
                ))}
                {t && (
                  <tr className="sum">
                    <td colSpan={4}>합계</td>
                    <td className="num">{num(t.incentive)}</td>
                    <td className="num">{num(t.extras)}</td>
                    <td className="num"><b>{num(t.total)}</b></td>
                    <td />
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {view.unassigned.length > 0 && (
            <>
              <h4>담당 미확인 ({view.unassigned.length}건)</h4>
              <div className="muted small">
                해결: 인센티브 &gt; 일자별 입력 &gt; 담당 [변경]에서 그날 담당자 지정 (정규직 포함), 또는 시급제 근무 기록의 "그날 계정" 입력
              </div>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>날짜</th><th>계정</th><th className="num">금액</th><th>사유</th></tr></thead>
                  <tbody>
                    {view.unassigned.map((u) => (
                      <tr key={`${u.date}-${u.manager_id}`}>
                        <td>{u.date}</td>
                        <td>{u.manager_name}</td>
                        <td className="num">{u.pending && !u.amount ? "고객사 수 미입력" : num(u.amount)}</td>
                        <td>{u.why}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </Panel>
  );
}
