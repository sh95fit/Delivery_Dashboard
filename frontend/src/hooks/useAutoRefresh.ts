import { useEffect, useState } from "react";

const KEY = "ll.autoRefresh";
/** 서버 캐시 TTL(오늘 20초)보다 짧은 주기는 의미가 없어 30초부터 */
export const REFRESH_OPTIONS = [30, 60, 120] as const;
type Pref = { on: boolean; sec: number };
const DEFAULT: Pref = { on: true, sec: 30 };

function read(): Pref {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (v && typeof v.on === "boolean" && (REFRESH_OPTIONS as readonly number[]).includes(v.sec)) return v;
  } catch {
    /* 저장값 손상 시 기본값 */
  }
  return DEFAULT;
}

export function useAutoRefresh() {
  const [pref, setPref] = useState<Pref>(read);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(pref));
    } catch {
      /* 저장 불가 환경 무시 */
    }
  }, [pref]);
  return {
    on: pref.on,
    sec: pref.sec,
    setOn: (on: boolean) => setPref((p) => ({ ...p, on })),
    setSec: (sec: number) => setPref((p) => ({ ...p, sec })),
  };
}
