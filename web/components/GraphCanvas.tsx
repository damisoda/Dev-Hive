"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphResponse } from "@/lib/types";

// react-force-graph-2d는 canvas 기반 클라 전용 → SSR 비활성 dynamic import.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const COLORS = { topic: "#4E68C7", auto: "#A9B4E0", content: "#CBD0DA" };

export function GraphCanvas({ data }: { data: GraphResponse }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 900, h: 620 });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // force-graph가 source/target를 노드 참조로 치환하므로 복사본 전달.
  const graph = useMemo(
    () => ({
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({ source: e.source, target: e.target, rel: e.rel, weight: e.weight })),
    }),
    [data]
  );

  return (
    <div ref={wrapRef} className="graph-wrap">
      <ForceGraph2D
        graphData={graph}
        width={size.w}
        height={size.h}
        backgroundColor="#FFFFFF"
        nodeRelSize={4}
        nodeVal={(n: any) => (n.kind === "topic" ? 12 : n.auto ? 3 : 1.5)}
        nodeColor={(n: any) => COLORS[n.kind as keyof typeof COLORS] ?? (n.auto ? COLORS.auto : COLORS.content)}
        nodeLabel={(n: any) => n.label}
        linkColor={() => "rgba(120,132,156,0.13)"}
        linkWidth={(l: any) => Math.max(0.3, (l.weight ?? 0.3) * 1.2)}
        cooldownTicks={120}
        nodeCanvasObjectMode={(n: any) => (n.kind === "topic" ? "after" : undefined)}
        nodeCanvasObject={(n: any, ctx: any, scale: number) => {
          if (n.kind !== "topic" || !n.label) return;
          const fs = 13 / scale;
          ctx.font = `700 ${fs}px Pretendard, -apple-system, sans-serif`;
          ctx.fillStyle = "#14161C";
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillText(n.label, n.x, n.y + 9 / scale);
        }}
      />
    </div>
  );
}
