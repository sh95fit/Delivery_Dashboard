import { useContext } from "react";
import type { CrudOp, MeResp } from "@/api/types";
import { MeContext } from "./shell";

/** 화면키·연산 권한 판정 — 마스터는 전부 허용, 그 외는 권한셋(grants) 기준 */
export function can(me: MeResp | null | undefined, page: string, op: CrudOp = "R"): boolean {
  if (!me) return false;
  if (me.is_super) return true;
  return Boolean(me.grants?.[page]?.[op]);
}

export function useCan(page: string, op: CrudOp = "R"): boolean {
  const me = useContext(MeContext);
  return can(me, page, op);
}
