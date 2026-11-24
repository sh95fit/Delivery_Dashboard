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

// styles.css 칩 클래스 (색 의미: ok=완료, warn=예상/대기, caution=주의, danger=오류)
export const STATUS_CHIP: Record<UserStatus, string> = {
  invited: "chip-warn", expired: "chip-caution", active: "chip-ok",
  inactive: "chip-danger", revoked: "chip-neutral", none: "chip-neutral",
};

export const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleString("ko-KR") : "-");

/** Gmail 작성 창 URL (받는 사람·제목·본문 미리 채움) */
export function gmailInviteUrl(email: string, setName: string | null, days: number) {
  const site = window.location.origin;
  const su = "[LunchLab 대시보드] 접속 초대";
  const body = [
    "안녕하세요.",
    "",
    `LunchLab 배송 대시보드에 초대되었습니다.${setName ? ` (권한: ${setName})` : ""}`,
    "",
    `1. 아래 주소에 접속합니다: ${site}`,
    `2. "Google로 로그인"을 누르고 이 메일을 받은 계정(${email})으로 로그인합니다.`,
    "",
    `초대는 ${days}일 동안 유효합니다. 기간이 지나면 관리자에게 재초대를 요청해 주세요.`,
  ].join("\n");
  const q = new URLSearchParams({ view: "cm", fs: "1", to: email, su, body });
  return `https://mail.google.com/mail/?${q.toString()}`;
}

export const openGmailInvite = (email: string, setName: string | null, days: number) =>
  window.open(gmailInviteUrl(email, setName, days), "_blank", "noopener");

const enc = (e: string) => encodeURIComponent(e);

export const listUsers = () => http<UserRow[]>("/api/users");
export const listPermSets = () => http<PermSetLite[]>("/api/permission-sets");
export type InviteResult = { email?: string; mail_sent: boolean; mail_error: string | null };
export const createUser = (b: UserInput) => post<InviteResult>("/api/users", b);
export const resendInvite = (email: string, days: number) =>
  post<InviteResult>(`/api/users/${enc(email)}/invitation/resend`, { days });
export const setUserPermSet = (email: string, permission_set_id: number) =>
  put<{ email: string }>(`/api/users/${enc(email)}/permission-set`, { permission_set_id });
export const setUserActive = (email: string, active: boolean) =>
  put<{ email: string }>(`/api/users/${enc(email)}/active`, { active });
export const revokeUserInvite = (email: string) =>
  del<{ email: string }>(`/api/users/${enc(email)}/invitation`);
export const deleteUser = (email: string) => del<{ email: string }>(`/api/users/${enc(email)}`);
export const clearInvite = (email: string) => del<{ email: string }>(`/api/users/${enc(email)}/invite-record`);