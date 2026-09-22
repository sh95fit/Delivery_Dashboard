import RequireAuth from "@/features/auth/RequireAuth";
import DashboardPage from "@/features/dashboard/DashboardPage";

export default function DashboardRoute() {
  return (
    <RequireAuth>
      <DashboardPage />
    </RequireAuth>
  );
}
