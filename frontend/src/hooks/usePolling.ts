import { useEffect, useRef } from "react";

export function usePolling(fn: () => void, intervalMs: number, enabled: boolean) {
  const ref = useRef(fn);
  ref.current = fn;

  useEffect(() => {
    if (!enabled) return;

    const id = setInterval(() => {
      ref.current();
    }, intervalMs);

    return () => clearInterval(id);
  }, [intervalMs, enabled]);
}
