import { createContext, useContext } from "react";
import type { MeResp } from "@/api/types";

/** 로그인 사용자 — AppShell에서 1회 조회해 모든 페이지에 공급 (페이지별 /api/me 중복 호출 제거) */
export const MeContext = createContext<MeResp | null>(null);
export const useMe = () => useContext(MeContext);

/** 모바일 사이드바 열기 — 셸 밖(로그인 화면 등)에서는 inShell=false */
export const ShellContext = createContext<{ inShell: boolean; openMobile: () => void }>({
  inShell: false,
  openMobile: () => {},
});
export const useShell = () => useContext(ShellContext);
