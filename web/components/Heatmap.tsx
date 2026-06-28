"use client";

// 학습 활동 — 올해(1월 1일~오늘) 읽기 히트맵을 벌집(육각) 셀로. {YYYY-MM-DD: 읽은 수}.
// 셀에 마우스를 올리면 날짜 + 읽은 글 수 툴팁. 가장자리 셀은 잘리지 않게 위치 보정.
import { useState } from "react";

function level(count: number): number {
  if (count <= 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  if (count <= 5) return 3;
  return 4;
}

type Day = { date: string; count: number };
type Tip = { label: string; cx: number; cleft: number; top: number; h: number; below: boolean; leftEdge: boolean };

export function Heatmap({ data }: { data: Record<string, number> }) {
  const [tip, setTip] = useState<Tip | null>(null);

  // 올해 날짜들만: 1월 1일 ~ 오늘.
  const today = new Date();
  const start = new Date(today.getFullYear(), 0, 1);
  const totalDays = Math.floor((today.getTime() - start.getTime()) / 86400000) + 1;

  const days: Day[] = [];
  for (let i = totalDays - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    days.push({ date: key, count: data[key] ?? 0 });
  }
  // 7행(요일축) × N주. 마지막 주가 부분이면 null로 채워 정렬 유지.
  const weeks = Math.ceil(days.length / 7);
  const rows: (Day | null)[][] = [];
  for (let r = 0; r < 7; r++) {
    const row: (Day | null)[] = [];
    for (let w = 0; w < weeks; w++) {
      const idx = w * 7 + r;
      row.push(idx < days.length ? days[idx] : null);
    }
    rows.push(row);
  }

  const label = (d: Day) => {
    // 키(YYYY-MM-DD) 문자열에서 직접 파싱 — new Date 재파싱의 타임존 시프트 회피.
    const [, m, day] = d.date.split("-");
    return `${+m}월 ${+day}일 · ${d.count > 0 ? `${d.count}건 읽음` : "학습 없음"}`;
  };

  return (
    <div className="hivemap" role="img" aria-label="올해 학습 기록">
      {rows.map((row, r) => (
        <div className={`hive-row${r % 2 === 1 ? " odd" : ""}`} key={r}>
          {row.map((d, w) =>
            d ? (
              <span
                key={d.date}
                className={`hive-cell lv${level(d.count)}`}
                onMouseEnter={(e) => {
                  const t = e.currentTarget;
                  setTip({
                    label: label(d),
                    cx: t.offsetLeft + t.offsetWidth / 2,
                    cleft: t.offsetLeft,
                    top: t.offsetTop,
                    h: t.offsetHeight,
                    below: t.offsetTop < 40, // 상단 행 → 툴팁을 아래로(위 잘림 방지)
                    leftEdge: t.offsetLeft < 64, // 좌측 끝 → 왼쪽 정렬(좌 잘림 방지)
                  });
                }}
                onMouseLeave={() => setTip(null)}
              />
            ) : (
              <span key={`e${r}-${w}`} className="hive-cell hive-empty" aria-hidden />
            )
          )}
        </div>
      ))}
      {tip && (
        <div
          className="hive-tip"
          style={{
            left: tip.leftEdge ? tip.cleft : tip.cx,
            top: tip.below ? tip.top + tip.h + 6 : tip.top,
            transform: `translate(${tip.leftEdge ? "0" : "-50%"}, ${tip.below ? "0" : "-118%"})`,
          }}
        >
          {tip.label}
        </div>
      )}
    </div>
  );
}
