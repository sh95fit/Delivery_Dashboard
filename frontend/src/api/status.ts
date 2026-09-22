import { http } from "./client";
import type { StatusResp } from "./types";

export const getStatus = (date: string) => http<StatusResp>(`/api/status/${date}`);
