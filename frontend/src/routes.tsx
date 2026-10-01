import { createBrowserRouter, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardRoute from "./pages/DashboardRoute";
import InternalTargetsRoute from "./pages/InternalTargetsRoute";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/", element: <DashboardRoute /> },
  { path: "/settings/internal", element: <InternalTargetsRoute /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
