import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { getMe } from "@/api/auth";
import Spinner from "@/components/ui/Spinner";

export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "ok" | "no">("checking");

  useEffect(() => {
    getMe()
      .then(() => setState("ok"))
      .catch(() => setState("no"));
  }, []);

  if (state === "checking") return <Spinner label="로그인 상태 확인 중…" />;
  if (state === "no") return <Navigate to="/login" replace />;
  return <>{children}</>;
}
