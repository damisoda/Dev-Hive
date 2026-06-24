// 학습 잔디 — 최근 26주 읽기 히트맵. {YYYY-MM-DD: 읽은 수} → 주(열)×요일(행) 그리드.
// 서버 컴포넌트(일반 Node 런타임이라 new Date 사용 OK).

const WEEKS = 26;

function level(count: number): number {
  if (count <= 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  return 3;
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
  const weeks: { date: string; count: number }[][] = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));

  return (
    <div className="hm" role="img" aria-label="최근 26주 학습 기록">
      {weeks.map((w, i) => (
        <div className="hm-col" key={i}>
          {w.map((d) => (
            <span key={d.date} className={`hm-cell lv${level(d.count)}`} title={`${d.date} · ${d.count}개`} />
          ))}
        </div>
      ))}
    </div>
  );
}
