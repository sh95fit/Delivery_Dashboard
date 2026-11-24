import { Link } from "react-router-dom";

export default function ForbiddenPage() {
  return (
    <div style={{ padding: "48px 24px", textAlign: "center" }}>
      <h2 style={{ marginBottom: 8 }}>접근 권한이 없습니다</h2>
      <p style={{ color: "#666", marginBottom: 20 }}>
        이 화면을 볼 권한이 없습니다. 필요하면 시스템 관리자에게 권한을 요청하세요.
      </p>
      <Link to="/">처음 화면으로</Link>
    </div>
  );
}
