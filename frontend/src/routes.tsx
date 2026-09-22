import { createBrowserRouter, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardRoute from "./pages/DashboardRoute";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/", element: <DashboardRoute /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
