/* [S3-P2d-2c] 경로선 겹침 정리 — 순수 함수 (지도 객체 없음)
   - offsetPath: 진행 방향 오른쪽으로 평행 이동 → 같은 길을 갔다 돌아오면 두 줄로 갈라져 보임
   - arrowPoints: 일정 간격마다 진행 방향 화살표 위치·각도 */
export type GeoPt = { lat: number; lng: number };
type Vec = { x: number; y: number };

const M_PER_DEG = 111_320;

/** 확대 단계별 화면 1px의 실제 거리(m) — 웹 메르카토르 */
export function metersPerPixel(zoom: number, lat: number): number {
    return (156_543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
}

/** 진행 방향 오른쪽으로 meters만큼 띄운 경로. 되돌아 나오는 지점(급회전)은 두 점으로 이어 고리처럼 보이게 함 */
export function offsetPath(path: GeoPt[], meters: number): GeoPt[] {
    if (path.length < 2 || meters <= 0) return path;
    const k = Math.cos((path[0].lat * Math.PI) / 180);
    const raw: Array<Vec | null> = [];
    for (let i = 0; i < path.length - 1; i++) {
    const dx = (path[i + 1].lng - path[i].lng) * M_PER_DEG * k;
    const dy = (path[i + 1].lat - path[i].lat) * M_PER_DEG;
    const len = Math.hypot(dx, dy);
    raw.push(len < 0.01 ? null : { x: dy / len, y: -dx / len });   // 오른쪽 법선
    }
    const first = raw.find((v): v is Vec => v != null);
    if (!first) return path;
    const n: Vec[] = [];
    let last: Vec = first;
    for (const v of raw) {
    if (v) last = v;
    n.push(last);
    }
    const move = (p: GeoPt, v: Vec): GeoPt => ({
    lat: p.lat + (v.y * meters) / M_PER_DEG,
    lng: p.lng + (v.x * meters) / (M_PER_DEG * k),
    });
    const out: GeoPt[] = [move(path[0], n[0])];
    for (let i = 1; i < path.length - 1; i++) {
    const a = n[i - 1];
    const b = n[i];
    if (a.x * b.x + a.y * b.y < -0.5) {
        out.push(move(path[i], a), move(path[i], b));
        continue;
    }
    const sx = a.x + b.x;
    const sy = a.y + b.y;
    const sl = Math.hypot(sx, sy);
    out.push(move(path[i], { x: sx / sl, y: sy / sl }));
    }
    out.push(move(path[path.length - 1], n[n.length - 1]));
    return out;
}

/** everyM 간격(첫 화살표는 간격 절반 지점)의 위치와 각도(북쪽 0°, 시계 방향) */
export function arrowPoints(path: GeoPt[], everyM: number, max = 300): Array<GeoPt & { deg: number }> {
    const out: Array<GeoPt & { deg: number }> = [];
    if (path.length < 2 || everyM <= 0) return out;
    const k = Math.cos((path[0].lat * Math.PI) / 180);
    let next = everyM / 2;
    let acc = 0;
    for (let i = 0; i < path.length - 1 && out.length < max; i++) {
    const a = path[i];
    const b = path[i + 1];
    const dx = (b.lng - a.lng) * M_PER_DEG * k;
    const dy = (b.lat - a.lat) * M_PER_DEG;
    const len = Math.hypot(dx, dy);
    if (len < 0.01) continue;
    const deg = (Math.atan2(dx, dy) * 180) / Math.PI;
    while (acc + len >= next && out.length < max) {
        const t = (next - acc) / len;
        out.push({ lat: a.lat + (b.lat - a.lat) * t, lng: a.lng + (b.lng - a.lng) * t, deg });
        next += everyM;
    }
    acc += len;
    }
    return out;
}
