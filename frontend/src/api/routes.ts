import { http, post } from "./client";
import type { AllRoutesResp, RouteSummary } from "./types";

export const getAllRoutes = (date: string) =>
  http<AllRoutesResp>(`/api/routes/${date}`);

export const getRoute = (date: string, managerId: number) =>
  http<RouteSummary>(`/api/routes/${date}/${managerId}`);

export const refreshRoute = (date: string, managerId: number) =>
  post<RouteSummary>(`/api/routes/${date}/${managerId}/refresh`, {});
