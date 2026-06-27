// 학습 활동 — 최근 14주 읽기 히트맵을 벌집(육각) 셀로 렌더. {YYYY-MM-DD: 읽은 수}.
// 시간축(언제 얼마나 읽었는지). 5단계 꿀색 스케일 · 짝수행 offset으로 벌집 인터록.
// 서버 컴포넌트(일반 Node 런타임이라 new Date 사용 OK).

const WEEKS = 14;

// 0~4단계(꿀색 스케일). 0=없음.
function level(count: number): number {
  if (count <= 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  if (count <= 5) return 3;
  return 4;
}

export function Heatmap({ data }: { data: Record<string, number> }) {
  const today = new Date();
  const totalDays = WEEKS * 7;
  const days: { date: string; count: number }[] = [];
  for (let i = totalDays - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    days.push({ date: key, count: data[key] ?? 0 });
  }
  // 7행(요일축) × WEEKS열(주). row r = 각 주의 같은 위치 셀.
  const rows: { date: string; count: number }[][] = [];
  for (let r = 0; r < 7; r++) {
    const row: { date: string; count: number }[] = [];
    for (let w = 0; w < WEEKS; w++) row.push(days[w * 7 + r]);
    rows.push(row);
  }

  return (
    <div className="hivemap" role="img" aria-label="최근 14주 학습 기록">
      {rows.map((row, r) => (
        <div className={`hive-row${r % 2 === 1 ? " odd" : ""}`} key={r}>
          {row.map((d) => (
            <span key={d.date} className={`hive-cell lv${level(d.count)}`} title={`${d.date} · ${d.count}개`} />
          ))}
        </div>
      ))}
    </div>
  );
}
