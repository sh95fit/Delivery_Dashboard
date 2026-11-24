import { useContext, type ReactNode } from "react";
import { MeContext } from "./shell";
import { can } from "./perm";
import ForbiddenPage from "@/pages/ForbiddenPage";

/** 화면 진입 가드 — R 권한 없으면 ForbiddenPage. superOnly면 시스템 마스터만. */
export default function RequirePage({ page, superOnly, children }:
  { page?: string; superOnly?: boolean; children: ReactNode }) {
  const me = useContext(MeContext);
  const ok = superOnly ? Boolean(me?.is_super) : page ? can(me, page, "R") : Boolean(me);
  return ok ? <>{children}</> : <ForbiddenPage />;
}
