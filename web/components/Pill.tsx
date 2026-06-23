import type { PillSpec } from "@/lib/viewmodel";

export function PillRow({ pills }: { pills: PillSpec[] }) {
  if (pills.length === 0) return null;
  return (
    <div className="pill-row">
      {pills.map((p, i) => (
        <span key={i} className="pill" style={{ color: p.fg, background: p.bg }}>
          {p.text}
        </span>
      ))}
    </div>
  );
}
