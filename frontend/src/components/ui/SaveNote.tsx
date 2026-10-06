export type SaveNoteState<S extends string = string> = { sec: S; ok: boolean; text: string; at: string };

export const nowHms = () =>
  new Date().toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul" });

export default function SaveNote({ note, sec, hide }: { note: SaveNoteState | null; sec: string; hide?: boolean }) {
  if (!note || note.sec !== sec || hide) return null;
  return (
    <span className={`save-note ${note.ok ? "ok" : "fail"}`} role="status" aria-live="polite">
      {note.ok ? "✓" : "✕"} {note.text} · {note.at}
    </span>
  );
}
