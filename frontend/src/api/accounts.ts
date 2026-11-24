import { http, post, put, del } from "./client";

export type Account = {
  id: number; email: string; active: boolean; is_super: boolean;
  activated_at: string | null; last_login_at: string | null; created_at: string | null;
  invitation_id: number | null; permission_set_name: string | null;
};
export type InviteState = "pending" | "expired" | "accepted" | "revoked";
export type Invitation = {
  id: number; email: string; status: string; state: InviteState; memo: string | null;
  invited_by: string | null; created_at: string; expires_at: string;
  accepted_at: string | null; revoked_by: string | null; revoked_at: string | null;
  has_rule: boolean;
};
export type InviteInput = { email: string; days: number; memo: string | null };

export const STATE_LABELS: Record<InviteState, string> = {
  pending: "대기", expired: "만료", accepted: "수락", revoked: "취소",
};
export const STATE_COLORS: Record<InviteState, string> = {
  pending: "#2563eb", expired: "#999", accepted: "#16a34a", revoked: "#c0392b",
};

export const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleString("ko-KR") : "-");

export const listAccounts = () => http<Account[]>("/api/accounts");
export const setAccountActive = (id: number, active: boolean) =>
  put<{ id: number; active: boolean }>(`/api/accounts/${id}/active`, { active });

export const listInvitations = () => http<Invitation[]>("/api/invitations");
export const createInvitation = (b: InviteInput) =>
  post<{ id: number; has_rule: boolean }>("/api/invitations", b);
export const revokeInvitation = (id: number) => del<{ id: number }>(`/api/invitations/${id}`);
