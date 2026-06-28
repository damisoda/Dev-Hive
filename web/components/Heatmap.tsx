"use client";

// 학습 활동 — 최근 14주 읽기 히트맵을 벌집(육각) 셀로. {YYYY-MM-DD: 읽은 수}.
// 셀에 마우스를 올리면 날짜 + 읽은 글 수 툴팁을 띄운다. 5단계 꿀색 스케일.
import { useState } from "react";

const WEEKS = 14;

function level(count: number): number {
  if (count <= 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  if (count <= 5) return 3;
  return 4;
}

export function Heatmap({ data }: { data: Record<string, number> }) {
  const [tip, setTip] = useState<{ label: string; left: number; top: number } | null>(null);

  const today = new Date();
  const totalDays = WEEKS * 7;
  const days: { date: string; count: number }[] = [];
  for (let i = totalDays - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    days.push({ date: key, count: data[key] ?? 0 });
  }
  const rows: { date: string; count: number }[][] = [];
  for (let r = 0; r < 7; r++) {
    const row: { date: string; count: number }[] = [];
    for (let w = 0; w < WEEKS; w++) row.push(days[w * 7 + r]);
    rows.push(row);
  }

  const label = (d: { date: string; count: number }) => {
    const dt = new Date(d.date);
    return `${dt.getMonth() + 1}월 ${dt.getDate()}일 · ${d.count > 0 ? `${d.count}건 읽음` : "학습 없음"}`;
  };

  return (
    <div className="hivemap" role="img" aria-label="최근 14주 학습 기록">
      {rows.map((row, r) => (
        <div className={`hive-row${r % 2 === 1 ? " odd" : ""}`} key={r}>
          {row.map((d) => (
            <span
              key={d.date}
              className={`hive-cell lv${level(d.count)}`}
              onMouseEnter={(e) => {
                const t = e.currentTarget;
                setTip({ label: label(d), left: t.offsetLeft + t.offsetWidth / 2, top: t.offsetTop });
              }}
              onMouseLeave={() => setTip(null)}
            />
          ))}
        </div>
      ))}
      {tip && (
        <div className="hive-tip" style={{ left: tip.left, top: tip.top }}>
          {tip.label}
        </div>
      )}
    </div>
  );
}
