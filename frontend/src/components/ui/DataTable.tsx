import type { ReactNode } from "react";

export default function DataTable({ columns, children }: { columns: string[]; children: ReactNode }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
      <thead>
        <tr>
          {columns.map((c) => (
            <th
              key={c}
              style={{ textAlign: "left", padding: "8px 10px", borderBottom: "2px solid #eee" }}
            >
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}
