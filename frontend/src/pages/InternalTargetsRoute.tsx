import RequireAuth from "@/features/auth/RequireAuth";
import InternalTargetsPage from "@/features/settings/InternalTargetsPage";

export default function InternalTargetsRoute() {
  return (
    <RequireAuth>
      <InternalTargetsPage />
    </RequireAuth>
  );
}
