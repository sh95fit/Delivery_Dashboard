import { useCallback, useEffect, useState } from "react";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const run = useCallback(() => {
    setLoading(true);
    setError("");
    return fn()
      .then((d) => {
        setData(d);
        setLoading(false);
        return d;
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
        throw e;
      });
  }, deps);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    fn()
      .then((d) => {
        if (!alive) return;
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, deps);

  return { data, loading, error, refetch: run };
}
