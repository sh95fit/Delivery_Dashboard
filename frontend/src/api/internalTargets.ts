import { del, http, post } from "./client";

export type TargetKind = "address" | "account";

export interface InternalTarget {
  id: number;
  kind: TargetKind;
  target_id: number;
  label?: string | null;
  name?: string | null;
  account_id?: number | null;
  account_name?: string | null;
  memo?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

export interface TargetCandidate {
  id: number;
  name?: string | null;
  account_id?: number | null;
  account_name?: string | null;
  address_count?: number | null;
  registered: boolean;
}

export const listInternalTargets = () =>
  http<{ items: InternalTarget[] }>("/api/internal-targets");

export const searchInternalTargets = (kind: TargetKind, q: string) =>
  http<{ items: TargetCandidate[] }>(
    `/api/internal-targets/search?kind=${kind}&q=${encodeURIComponent(q)}`,
  );

export const addInternalTarget = (body: { kind: TargetKind; target_id: number; memo: string | null }) =>
  post<{ ok: boolean; id: number }>("/api/internal-targets", body);

export const deleteInternalTarget = (id: number) =>
  del<{ ok: boolean }>(`/api/internal-targets/${id}`);
