import type { ReactNode } from "react";
import Icon from "./Icon";
import { useShell } from "./shell";

export default function PageLayout({
  title,
  children,
  right,
}: {
  title: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  const { inShell, openMobile } = useShell();
  return (
    <>
      <header className="topbar">
        {inShell && (
          <button className="burger" onClick={openMobile} aria-label="메뉴 열기">
            <Icon name="menu" size={20} />
          </button>
        )}
        <h1>{title}</h1>
        {right}
      </header>
      <div className="page">{children}</div>
    </>
  );
}
