import { createBrowserRouter, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import AppShell from "./layouts/AppShell";
import DashboardPage from "./features/dashboard/DashboardPage";
import InternalTargetsPage from "./features/settings/InternalTargetsPage";
import ManagersPage from "./features/settings/ManagersPage";
import VehiclesPage from "./features/settings/VehiclesPage";
import WorkersPage from "./features/settings/WorkersPage";


export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <AppShell />, // 인증 확인 1회 + 사이드바
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/settings/internal", element: <InternalTargetsPage /> },
      { path: "/settings/managers", element: <ManagersPage /> },
      { path: "/settings/workers", element: <WorkersPage /> },
      { path: "/settings/vehicles", element: <VehiclesPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
