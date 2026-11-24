import { useSearchParams } from "react-router-dom";

const MESSAGES: Record<string, string> = {
  not_invited: "초대받은 사용자만 이용할 수 있습니다. 관리자에게 초대를 요청하세요.",
  inactive: "비활성화된 계정입니다. 관리자에게 문의하세요.",
  expired: "초대 기간이 만료되었습니다. 관리자에게 재초대를 요청하세요.",
};

export default function LoginPage() {
  const [params] = useSearchParams();
  const code = params.get("error");
  const msg = code ? MESSAGES[code] ?? "로그인할 수 없습니다. 관리자에게 문의하세요." : null;

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 className="login-title">LunchLab 배송 대시보드</h1>
        {msg ? (
          <p className="error-box">{msg}</p>
        ) : (
          <p className="login-desc">세션이 없거나 만료되었습니다. 초대받은 구글 계정으로 로그인하세요.</p>
        )}
        <a href="/api/auth/login" className="btn btn-primary login-btn">
          {msg ? "다른 구글 계정으로 로그인" : "구글 계정으로 로그인"}
        </a>
      </div>
    </div>
  );
}
