import DataTable from "@/components/ui/DataTable";
import type { ManagerRow } from "@/api/types";

export default function ManagerTable({ rows }: { rows: ManagerRow[] }) {
  return (
    <DataTable columns={["매니저", "배송지", "식수", "고객사"]}>
      {rows.map((m) => (
        <tr key={m.manager_id}>
          <td style={{ padding: "8px 10px", borderBottom: "1px solid #f0f0f0" }}>{m.manager_name ?? m.manager_id}</td>
          <td style={{ padding: "8px 10px", borderBottom: "1px solid #f0f0f0" }}>{m.stops}</td>
          <td style={{ padding: "8px 10px", borderBottom: "1px solid #f0f0f0" }}>{m.meals}</td>
          <td style={{ padding: "8px 10px", borderBottom: "1px solid #f0f0f0" }}>{m.accounts}</td>
        </tr>
      ))}
    </DataTable>
  );
}
