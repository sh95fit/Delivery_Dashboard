import { http, post, put, del } from "./client";

export type Op = "R" | "C" | "U" | "D";
export const OPS: Op[] = ["R", "C", "U", "D"];
export const OP_LABELS: Record<Op, string> = { R: "보기", C: "생성", U: "수정", D: "삭제" };

// 백엔드 app/permissions.py PAGE_KEYS와 같은 순서·같은 12개
export const PAGE_KEYS = [
  "dashboard", "worklogs", "incentive", "logistics", "vehicles",
  "workers", "managers", "internal",
  "packing", "sales", "analysis", "simulation",
] as const;
export type PageKey = (typeof PAGE_KEYS)[number];

export const PAGE_LABELS: Record<PageKey, string> = {
  dashboard: "대시보드", worklogs: "근무 기록", incentive: "인센티브·수당", logistics: "물류비",
  vehicles: "차량·지출", workers: "인력", managers: "매니저 계정", internal: "직원식",
  packing: "포장 그룹(준비중)", sales: "매출 관리(준비중)", analysis: "매출·비용 분석(준비중)",
  simulation: "시뮬레이션(준비중)",
};

export type OpMap = Record<Op, boolean>;
export type Grants = Record<string, Partial<OpMap> | undefined>;
export type CleanGrants = Record<PageKey, OpMap>;

export type PermissionSet = {
  id: number; name: string; grants: Grants; builtin: boolean; memo: string | null; rule_count: number;
};
export type RuleKind = "email" | "domain";
export type AccessRule = {
  id: number; kind: RuleKind; value: string; permission_set_id: number;
  permission_set_name: string | null; active: boolean; memo: string | null;
};
export type SetInput = { name: string; grants: CleanGrants; memo: string | null };
export type RuleInput = {
  kind: RuleKind; value: string; permission_set_id: number; active: boolean; memo: string | null;
};

/** PAGE_KEYS 12개만 남기고(옛 키 settings 등 제거) R 없으면 C/U/D 해제 */
export function cleanGrants(g: Grants | null | undefined): CleanGrants {
  const out = {} as CleanGrants;
  for (const k of PAGE_KEYS) {
    const src = g?.[k] ?? {};
    const r = Boolean(src.R);
    out[k] = { R: r, C: r && Boolean(src.C), U: r && Boolean(src.U), D: r && Boolean(src.D) };
  }
  return out;
}

/** 체크 토글: R 끄면 C/U/D도 끔, C/U/D 켜면 R도 켬 */
export function toggleOp(g: CleanGrants, page: PageKey, op: Op): CleanGrants {
  const cur = g[page];
  const on = !cur[op];
  let next: OpMap;
  if (op === "R") next = on ? { ...cur, R: true } : { R: false, C: false, U: false, D: false };
  else next = { ...cur, [op]: on, R: on ? true : cur.R };
  return { ...g, [page]: next };
}

export const listSets = () => http<PermissionSet[]>("/api/permission-sets");
export const createSet = (b: SetInput) => post<{ id: number }>("/api/permission-sets", b);
export const updateSet = (id: number, b: SetInput) => put<{ id: number }>(`/api/permission-sets/${id}`, b);
export const deleteSet = (id: number) => del<{ id: number }>(`/api/permission-sets/${id}`);

export const listRules = () => http<AccessRule[]>("/api/access-rules");
export const createRule = (b: RuleInput) => post<{ id: number }>("/api/access-rules", b);
export const updateRule = (id: number, b: RuleInput) => put<{ id: number }>(`/api/access-rules/${id}`, b);
export const deleteRule = (id: number) => del<{ id: number }>(`/api/access-rules/${id}`);
