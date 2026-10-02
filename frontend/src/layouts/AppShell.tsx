import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { getMe } from "@/api/auth";
import type { MeResp } from "@/api/types";
import Spinner from "@/components/ui/Spinner";
import Icon from "./Icon";
import { NAV } from "./nav";
import { MeContext, ShellContext } from "./shell";

const KEY = "ll.sidebar.collapsed";
const MOBILE = "(max-width: 900px)";

function readCollapsed() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

function useIsMobile() {
  const [m, setM] = useState(() => window.matchMedia(MOBILE).matches);
  useEffect(() => {
    const mq = window.matchMedia(MOBILE);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return m;
}

export default function AppShell() {
  const [me, setMe] = useState<MeResp | null>(null);
  const [auth, setAuth] = useState<"checking" | "ok" | "no">("checking");
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isMobile = useIsMobile();
  const { pathname } = useLocation();

  useEffect(() => {
    getMe()
      .then((m) => {
        setMe(m);
        setAuth("ok");
      })
      .catch(() => setAuth("no"));
  }, []);

  useEffect(() => setMobileOpen(false), [pathname]);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch {
      /* 저장 불가 환경 무시 */
    }
    // 지도 등 폭 의존 컴포넌트가 사이드바 전환 후 다시 맞추도록
    const t = window.setTimeout(() => window.dispatchEvent(new Event("resize")), 220);
    return () => window.clearTimeout(t);
  }, [collapsed]);

  if (auth === "checking") return <Spinner label="로그인 상태 확인 중…" />;
  if (auth === "no") return <Navigate to="/login" replace />;

  const isCollapsed = collapsed && !isMobile;
  const cls = ["shell", isCollapsed ? "collapsed" : "", mobileOpen ? "mobile-open" : ""].join(" ").trim();

  return (
    <MeContext.Provider value={me}>
      <ShellContext.Provider value={{ inShell: true, openMobile: () => setMobileOpen(true) }}>
        <div className={cls}>
          <aside className="sb">
            <div className="sb-head">
              <span className="sb-brand">LunchLab 배송</span>
              <button
                className="sb-toggle"
                onClick={() => setCollapsed((c) => !c)}
                title={isCollapsed ? "메뉴 펼치기" : "메뉴 접기"}
                aria-label={isCollapsed ? "메뉴 펼치기" : "메뉴 접기"}
              >
                <Icon name={isCollapsed ? "right" : "left"} />
              </button>
            </div>

            <nav className="sb-nav">
              {NAV.map((sec) => (
                <div key={sec.section}>
                  <div className="sb-sec">{sec.section}</div>
                  {sec.items.map((it) =>
                    it.ready ? (
                      <NavLink
                        key={it.to}
                        to={it.to}
                        end={it.to === "/"}
                        className={({ isActive }) => `sb-item${isActive ? " active" : ""}`}
                        title={isCollapsed ? it.label : undefined}
                      >
                        <Icon name={it.icon} />
                        <span className="sb-label">{it.label}</span>
                      </NavLink>
                    ) : (
                      <span
                        key={it.to}
                        className="sb-item off"
                        title={`${it.label} — 준비 중${it.step ? ` (${it.step})` : ""}`}
                      >
                        <Icon name={it.icon} />
                        <span className="sb-label">{it.label}</span>
                        <span className="sb-tag">준비</span>
                      </span>
                    ),
                  )}
                </div>
              ))}
            </nav>

            <div className="sb-foot" title={me?.email}>
              {me?.email}
              {me?.is_admin ? " · 관리자" : ""}
            </div>
          </aside>

          <div className="scrim" onClick={() => setMobileOpen(false)} />

          <div className="main">
            <Outlet />
          </div>
        </div>
      </ShellContext.Provider>
    </MeContext.Provider>
  );
}
