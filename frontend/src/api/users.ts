import { http, post, put, del } from "./client";

export type UserStatus = "invited" | "expired" | "active" | "inactive" | "revoked" | "none";
export type UserRow = {
  email: string;
  permission_set_id: number | null;
  permission_set_name: string | null;
  status: UserStatus;
  days_left: number | null;
  is_super: boolean;
  is_me: boolean;
  can_deactivate: boolean;
  last_login_at: string | null;
  expires_at: string | null;
  memo: string | null;
};
export type PermSetLite = { id: number; name: string };
export type UserInput = { email: string; permission_set_id: number; days: number; memo: string | null };

export const statusLabel = (u: UserRow) =>
  ({
    invited: `초대대기 D-${u.days_left ?? 0}`,
    expired: "초대만료",
    active: "활성",
    inactive: "비활성",
    revoked: "초대취소",
    none: "초대 전",
  })[u.status];

export const STATUS_COLORS: Record<UserStatus, string> = {
  invited: "#2563eb", expired: "#999", active: "#16a34a",
  inactive: "#c0392b", revoked: "#999", none: "#999",
};

export const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleString("ko-KR") : "-");

const enc = (e: string) => encodeURIComponent(e);

export const listUsers = () => http<UserRow[]>("/api/users");
export const listPermSets = () => http<PermSetLite[]>("/api/permission-sets");
export const createUser = (b: UserInput) => post<{ email: string }>("/api/users", b);
export const setUserPermSet = (email: string, permission_set_id: number) =>
  put<{ email: string }>(`/api/users/${enc(email)}/permission-set`, { permission_set_id });
export const setUserActive = (email: string, active: boolean) =>
  put<{ email: string }>(`/api/users/${enc(email)}/active`, { active });
export const revokeUserInvite = (email: string) =>
  del<{ email: string }>(`/api/users/${enc(email)}/invitation`);
