// Spinner.tsx
export default function Spinner({ label = "불러오는 중…" }: { label?: string }) {
  return <p className="spinner">{label}</p>;
}
