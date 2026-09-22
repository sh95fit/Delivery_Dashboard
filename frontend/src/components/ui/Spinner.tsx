export default function Spinner({ label = "불러오는 중…" }: { label?: string }) {
    return <p style={{ padding: 24, color: "#666" }}>{label}</p>;
  }
  