import Button from "./Button";
import { REFRESH_OPTIONS } from "@/hooks/useAutoRefresh";

type Props = {
  live: boolean; on: boolean; sec: number; busy: boolean; lastAt: Date | null;
  onToggle: (on: boolean) => void; onSec: (sec: number) => void; onRefresh: () => void;
};

export default function RefreshControl({ live, on, sec, busy, lastAt, onToggle, onSec, onRefresh }: Props) {
  const time = lastAt ? lastAt.toLocaleTimeString("ko-KR", { hour12: false }) : "-";
  return (
    <div className="refresh">
      {live && (
        <>
          <label className="switch" title="오늘·진행 중인 날짜만 자동 갱신됩니다">
            <input type="checkbox" checked={on} onChange={(e) => onToggle(e.target.checked)} />
            <span className="switch-track" />
            자동 갱신
          </label>
          <select className="input input-sm" value={sec} disabled={!on}
            onChange={(e) => onSec(Number(e.target.value))} aria-label="갱신 주기">
            {REFRESH_OPTIONS.map((s) => (
              <option key={s} value={s}>{s < 60 ? `${s}초` : `${s / 60}분`}</option>
            ))}
          </select>
          {on && <span className="live-dot" aria-hidden="true" />}
        </>
      )}
      <span>갱신 {time}</span>
      <Button size="sm" onClick={onRefresh} disabled={busy}>{busy ? "갱신 중…" : "새로고침"}</Button>
    </div>
  );
}
