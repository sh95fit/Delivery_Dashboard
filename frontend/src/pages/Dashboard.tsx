import { useEffect, useMemo, useState } from "react";
import { api, StatusResp, DeliveryResp, StatusState } from "../api";

const STATE_LABEL: Record<StatusState, string> = {
  PREVIEW: "미리보기",
  LIVE: "진행 중",
  RESULT: "완료",
  NONE: "데이터 없음",
};
const STATE_COLOR: Record<StatusState, string> = {
  PREVIEW: "#8b8b00",
  LIVE: "#c62828",
  RESULT: "#2e7d32",
  NONE: "#9e9e9e",
};

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function Dashboard() {
  const [date, setDate] = useState(today());
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [delivery, setDelivery] = useState<DeliveryResp | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setError("");
    Promise.all([api.status(date), api.deliveries(date)])
      .then(([s, d]) => {
        if (!alive) return;
        setStatus(s);
        setDelivery(d);
      })
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [date]);

  const rows = useMemo(() => delivery?.managers ?? [], [delivery]);

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, margin: 0 }}>배송 대시보드</h1>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        {status && (
          <span style={{ ...badge, background: STATE_COLOR[status.state] }}>
            {STATE_LABEL[status.state]}
          </span>
        )}
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#666" }}>
          마감: 배송일 전날 14:30 KST
        </span>
      </header>

      {error && <p style={{ color: "#c62828" }}>오류: {error}</p>}

      {status && (
        <section style={grid}>
          <Card title="배송지">
            {status.state === "PREVIEW" && status.estimate
              ? `${status.estimate.total} (예상)`
              : status.progress.total}
          </Card>
          <Card title="완료">{status.progress.completed}</Card>
          <Card title="미배정">{status.progress.unassigned}</Card>
          <Card title="미완료">{status.incomplete}</Card>
          {status.state === "PREVIEW" && status.estimate && (
            <Card title="예상 식수">{status.estimate.estimated_meals}</Card>
          )}
        </section>
      )}

      <h2 style={{ fontSize: 16, margin: "24px 0 8px" }}>매니저별 현황</h2>
      <table style={table}>
        <thead>
          <tr>
            <th style={th}>매니저</th>
            <th style={th}>배송지</th>
            <th style={th}>식수</th>
            <th style={th}>고객사</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.manager_id}>
              <td style={td}>{m.manager_id}</td>
              <td style={td}>{m.stops}</td>
              <td style={td}>{m.meals}</td>
              <td style={td}>{m.accounts}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && !error && <p>해당 날짜 데이터가 없습니다.</p>}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={card}>
      <div style={{ fontSize: 12, color: "#666" }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{children}</div>
    </div>
  );
}

const badge: React.CSSProperties = {
  color: "#fff",
  padding: "4px 10px",
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 600,
};
const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: 12,
};
const card: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  padding: "12px 16px",
  background: "#fff",
};
const table: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  background: "#fff",
};
const th: React.CSSProperties = { textAlign: "left", padding: "8px 10px", borderBottom: "2px solid #eee" };
const td: React.CSSProperties = { padding: "8px 10px", borderBottom: "1px solid #f0f0f0" };
