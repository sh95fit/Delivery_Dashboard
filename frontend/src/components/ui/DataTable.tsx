import type { ReactNode } from "react";

export type Col = string | { label: string; num?: boolean };

export default function DataTable({ columns, children }: { columns: Col[]; children: ReactNode }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            {columns.map((c) => {
              const col = typeof c === "string" ? { label: c } : c;
              return <th key={col.label} className={col.num ? "num" : undefined}>{col.label}</th>;
            })}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
