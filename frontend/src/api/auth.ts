import { http } from "./client";
import type { MeResp } from "./types";

export const getMe = () => http<MeResp>("/api/me");
