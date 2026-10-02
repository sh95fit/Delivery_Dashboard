import { useEffect, useRef } from "react";

export function usePolling(fn: () => void, intervalMs: number, enabled: boolean) {
  const ref = useRef(fn);
  ref.current = fn;

  useEffect(() => {
    if (!enabled) return;
    let id: number | undefined;

    const start = () => {
      if (id === undefined) id = window.setInterval(() => ref.current(), intervalMs);
    };
    const stop = () => {
      if (id !== undefined) {
        window.clearInterval(id);
        id = undefined;
      }
    };
    const onVisibility = () => {
      if (document.hidden) {
        stop();
      } else {
        ref.current(); // 돌아오면 즉시 1회 갱신
        start();
      }
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [intervalMs, enabled]);
}
