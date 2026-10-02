import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "ghost" | "danger";
  size?: "sm" | "md";
};

export default function Button({ variant = "default", size = "md", className, type = "button", ...rest }: Props) {
  const cls = ["btn", variant !== "default" ? `btn-${variant}` : "", size === "sm" ? "btn-sm" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return <button type={type} className={cls} {...rest} />;
}
