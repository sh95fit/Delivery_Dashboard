import { http, post } from "./client";
import type { AllRoutesResp, PreviewAllStatus, RouteLegsResp, RoutePreview, RouteSummary } from "./types";

export const getAllRoutes = (date: string) =>
  http<AllRoutesResp>(`/api/routes/${date}`);

export const getRoute = (date: string, managerId: number) =>
  http<RouteSummary>(`/api/routes/${date}/${managerId}`);

export const refreshRoute = (date: string, managerId: number) =>
  post<RouteSummary>(`/api/routes/${date}/${managerId}/refresh`, {});

/* S3-P2d-2b-2 실제 경로(실선) · 남은 경로 미리보기(점선, 버튼으로만 계산) */
export const getRouteLegs = (date: string) =>
  http<RouteLegsResp>(`/api/routes/${date}/legs`);

export const previewRoute = (date: string, managerId: number) =>
  post<RoutePreview>(`/api/routes/${date}/${managerId}/preview`, {});

export const startPreviewAll = (date: string) =>
  post<PreviewAllStatus>(`/api/routes/${date}/preview-all`, {});

export const getPreviewAll = (date: string) =>
  http<PreviewAllStatus>(`/api/routes/${date}/preview-all`);
