import { createBrowserRouter, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import AppShell from "./layouts/AppShell";
import DashboardPage from "./features/dashboard/DashboardPage";
import InternalTargetsPage from "./features/settings/InternalTargetsPage";
import ManagersPage from "./features/settings/ManagersPage";
import VehiclesPage from "./features/settings/VehiclesPage";
import WorkersPage from "./features/settings/WorkersPage";
import WorkLogPage from "./features/worklogs/WorkLogPage";
import IncentivePage from "./features/incentive/IncentivePage";
import LogisticsPage from "./features/logistics/LogisticsPage";
import RequirePage from "./layouts/RequirePage";


export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <AppShell />, // 인증 확인 1회 + 사이드바
    children: [
      { path: "/", element: <RequirePage page="dashboard"><DashboardPage /></RequirePage> },
      { path: "/settings/internal", element: <RequirePage page="internal"><InternalTargetsPage /></RequirePage> },
      { path: "/settings/managers", element: <RequirePage page="managers"><ManagersPage /></RequirePage> },
      { path: "/settings/workers", element: <RequirePage page="workers"><WorkersPage /></RequirePage> },
      { path: "/settings/vehicles", element: <RequirePage page="vehicles"><VehiclesPage /></RequirePage> },
      { path: "/ops/work", element: <RequirePage page="worklogs"><WorkLogPage /></RequirePage> },
      { path: "/finance/incentive", element: <RequirePage page="incentive"><IncentivePage /></RequirePage> },
      { path: "/finance/cost", element: <RequirePage page="logistics"><LogisticsPage /></RequirePage> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
