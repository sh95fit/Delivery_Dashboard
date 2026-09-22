export default function LoginPage() {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          background: "#f6f7f9",
        }}
      >
        <div
          style={{
            background: "#fff",
            padding: "40px 48px",
            borderRadius: 12,
            boxShadow: "0 8px 30px rgba(0,0,0,.08)",
            textAlign: "center",
          }}
        >
          <h1 style={{ margin: "0 0 8px" }}>LunchLab 배송 대시보드</h1>
          <p style={{ color: "#555", margin: "0 0 24px" }}>
            세션이 없거나 만료되었습니다. 허용된 회사 계정으로 다시 로그인하세요.
          </p>
          <a
            href="/admin"
            style={{
              display: "inline-block",
              padding: "12px 24px",
              borderRadius: 8,
              background: "#111",
              color: "#fff",
              textDecoration: "none",
              fontWeight: 600,
            }}
          >
            구글 계정으로 로그인
          </a>
        </div>
      </div>
    );
  }
  