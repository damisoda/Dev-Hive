"use client";

import { forceCollide } from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphResponse } from "@/lib/types";

// react-force-graph-2d는 canvas 기반 클라 전용. next/dynamic은 ref를 안 넘기므로(힘 튜닝에 ref 필요)
// effect에서 직접 지연 import(SSR 회피) 후 ref를 단 컴포넌트로 렌더한다.

const COLORS = {
  topic: "#4E68C7",
  auto: "#A9B4E0",
  content: "#CBD0DA",
  highlight: "#D9A441",
  highlightSoft: "#FFF3D8",
};

type GraphNode = GraphResponse["nodes"][number];

type GraphLink = {
  source: string | GraphNode;
  target: string | GraphNode;
  rel: string;
  weight: number;
};

export type GraphHighlight = {
  focusId?: string;
  contentId?: string;
  topicId?: string;
  isNew?: boolean;
};

function linkNodeId(node: string | { id?: string }) {
  return typeof node === "string" ? node : node.id;
}

function baseNodeVal(n: GraphNode) {
  if (n.kind === "topic") return 14;
  if (n.auto) return 3;
  return 1.5;
}

export function GraphCanvas({ data, highlight }: { data: GraphResponse; highlight?: GraphHighlight }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 900, h: 620 });
  const [FG, setFG] = useState<any>(null);

  useEffect(() => {
    let alive = true;
    import("react-force-graph-2d").then((m) => {
      if (alive) setFG(() => m.default);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const highlightIds = useMemo(
    () => new Set([highlight?.focusId, highlight?.contentId, highlight?.topicId].filter(Boolean) as string[]),
    [highlight?.contentId, highlight?.focusId, highlight?.topicId]
  );

  // force-graph가 source/target를 노드 참조로 치환하므로 복사본 전달.
  const graph = useMemo(
    () => ({
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({ source: e.source, target: e.target, rel: e.rel, weight: e.weight })),
    }),
    [data]
  );

  // 라벨 겹침 폴리시: 토픽 노드 강한 반발 + 충돌 반경 크게 → 7 대주제가 서로 밀려나 라벨이 안 겹친다.
  // similar_to 링크는 약하게(헤어볼 방지), belongs_to는 적당한 거리로 콘텐츠를 주제 주변에 모은다.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !FG) return;
    fg.d3Force("charge")?.strength((n: any) => (n.kind === "topic" ? -480 : -55));
    const link = fg.d3Force("link");
    if (link) {
      link
        .distance((l: any) => (l.rel === "belongs_to" ? 64 : 36))
        .strength((l: any) => (l.rel === "similar_to" ? 0.04 : 0.45));
    }
    fg.d3Force(
      "collide",
      forceCollide((n: any) => (n.kind === "topic" ? 48 : n.auto ? 10 : 6)).strength(0.9)
    );
    fg.d3ReheatSimulation?.();
  }, [FG, graph]);

  useEffect(() => {
    if (!highlightIds.size) return;
    window.history.replaceState(null, "", window.location.pathname);
  }, [highlightIds]);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !highlightIds.size) return;

    let raf = 0;
    const started = performance.now();
    const tick = () => {
      fg.refresh?.();
      if (performance.now() - started < 5600) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [highlightIds]);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !FG || !highlight?.focusId) return;

    const timer = window.setTimeout(() => {
      const node = graph.nodes.find((n) => n.id === highlight.focusId) as any;
      if (!node || typeof node.x !== "number" || typeof node.y !== "number") return;
      fg.centerAt?.(node.x, node.y, 1200);
      fg.zoom?.(node.kind === "topic" ? 3.0 : 4.2, 1200);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [FG, graph, highlight?.focusId]);

  const ForceGraph2D = FG;

  return (
    <div ref={wrapRef} className="graph-wrap">
      {ForceGraph2D && (
        <ForceGraph2D
          ref={fgRef}
          graphData={graph}
          width={size.w}
          height={size.h}
          backgroundColor="#FFFFFF"
          nodeRelSize={4}
          nodeVal={(n: GraphNode) => {
            if (n.id === highlight?.focusId) return n.kind === "topic" ? 18 : 5;
            if (highlightIds.has(n.id)) return n.kind === "topic" ? 16 : 3.5;
            return baseNodeVal(n);
          }}
          nodeColor={(n: GraphNode) => {
            if (n.id === highlight?.focusId) return COLORS.highlight;
            if (highlightIds.has(n.id)) return "#E7BD62";
            return COLORS[n.kind as keyof typeof COLORS] ?? (n.auto ? COLORS.auto : COLORS.content);
          }}
          nodeLabel={(n: GraphNode) => n.label}
          linkColor={(l: GraphLink) => {
            const source = linkNodeId(l.source);
            const target = linkNodeId(l.target);
            return source && target && highlightIds.has(source) && highlightIds.has(target)
              ? "rgba(217,164,65,0.56)"
              : "rgba(120,132,156,0.11)";
          }}
          linkWidth={(l: GraphLink) => {
            const source = linkNodeId(l.source);
            const target = linkNodeId(l.target);
            if (source && target && highlightIds.has(source) && highlightIds.has(target)) return 2.2;
            return Math.max(0.3, l.weight ?? 0.3);
          }}
          d3VelocityDecay={0.32}
          cooldownTicks={160}
          nodeCanvasObjectMode={(n: GraphNode) => (n.kind === "topic" || highlightIds.has(n.id) ? "after" : undefined)}
          nodeCanvasObject={(n: GraphNode & { x: number; y: number }, ctx: CanvasRenderingContext2D, scale: number) => {
            const isFocus = n.id === highlight?.focusId;
            const isHighlighted = highlightIds.has(n.id);

            if (isHighlighted) {
              const radius = (isFocus ? 16 : 11) / scale;
              ctx.beginPath();
              ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
              ctx.strokeStyle = isFocus ? "rgba(217,164,65,0.92)" : "rgba(217,164,65,0.7)";
              ctx.lineWidth = (isFocus ? 2.4 : 1.6) / scale;
              ctx.stroke();
            }

            if ((n.kind !== "topic" && !isFocus) || !n.label) return;
            const fs = (n.kind === "topic" ? 13 : 12) / scale;
            ctx.font = `700 ${fs}px Pretendard, -apple-system, sans-serif`;
            const tw = ctx.measureText(n.label).width;
            const padX = 6 / scale;
            const padY = 3.5 / scale;
            const bx = n.x - tw / 2 - padX;
            const by = n.y + 9 / scale;
            const bw = tw + padX * 2;
            const bh = fs + padY * 2;
            const r = 4 / scale;
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, r);
            else ctx.rect(bx, by, bw, bh);
            ctx.fillStyle = isFocus ? COLORS.highlightSoft : "rgba(255,255,255,0.92)";
            ctx.fill();
            ctx.fillStyle = "#14161C";
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillText(n.label, n.x, by + padY);
          }}
        />
      )}
    </div>
  );
}
