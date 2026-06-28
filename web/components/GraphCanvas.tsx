"use client";

import { forceCollide } from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphResponse } from "@/lib/types";
import { ReadModal } from "@/components/ReadModal";

// react-force-graph-2d는 canvas 기반 클라 전용. next/dynamic은 ref를 안 넘기므로(힘 튜닝에 ref 필요)
// effect에서 직접 지연 import(SSR 회피) 후 ref를 단 컴포넌트로 렌더한다.

/** 노드 kind → 기본 fill 색상 (hex only — hexRgba() 안전 보장) */
const NODE_COLORS: Record<string, string> = {
  topic: "#4E68C7",
  auto: "#A9B4E0",
  content: "#CBD0DA",
};

const C = {
  urlFocus: "#D9A441",
  urlFocusSoft: "#FFF3D8",
  urlHL: "#E7BD62",
  path: "#E1483B",          // 읽은 콘텐츠 / 추천 경로 — 빨강
  pathHover: "#C9352A",     // 읽은 콘텐츠 노드 호버 시 더 진한 빨강
  pathGlow: "rgba(225,72,59,0.55)",
  pathGlowHover: "rgba(225,72,59,0.85)",
  hover: "#fbbf24",         // 비경로 노드 호버 색상 (앰버/골드)
  hoverGlow: "rgba(251,191,36,0.65)",
} as const;

/** "#RRGGBB" → "rgba(r,g,b,a)" */
function hexRgba(hex: string, a: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

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

type SelectedNode = {
  id: string;
  label: string;
  kind: string;
  contentId?: number;
};

function linkNodeId(node: string | { id?: string }) {
  return typeof node === "string" ? node : node.id;
}

function baseNodeVal(n: GraphNode) {
  if (n.kind === "topic") return n.auto ? 3 : 9; // 대주제 굵게 / 하위 노드만 더 축소
  return 2; // 콘텐츠 얇게
}

function parseContentId(nodeId: string): number | undefined {
  const m = nodeId.match(/^content:(\d+)$/);
  return m ? Number(m[1]) : undefined;
}

function GraphNodeAutoOpen({ openFn }: { openFn: () => void }) {
  useEffect(() => { openFn(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export function GraphCanvas({
  data,
  highlight,
  loggedIn = false,
  pathIds = [],
}: {
  data: GraphResponse;
  highlight?: GraphHighlight;
  loggedIn?: boolean;
  pathIds?: string[];
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set()); // 접힌 노드(그 하위 콘텐츠 숨김). 초기 빈 셋 = 전부 표시
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 900, h: 620 });
  const [FG, setFG] = useState<any>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [selectKey, setSelectKey] = useState(0);

  // 호버는 고빈도 갱신이므로 ref + fg.refresh() 패턴 (state re-render 우회).
  const hoveredNodeRef = useRef<GraphNode | null>(null);

  const pathIdsSet = useMemo(() => new Set(pathIds), [pathIds]);

  useEffect(() => {
    let alive = true;
    import("react-force-graph-2d").then((m) => {
      if (alive) setFG(() => m.default);
    });
    return () => { alive = false; };
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

  // 전체 표시: 대주제 + auto 하위노드 + 콘텐츠 서브노드를 한 번에. (초기 = 전부 보임)
  // 노드(대주제·auto)를 클릭하면 collapsed에 담겨 그에 속한 콘텐츠만 접힌다(토픽 노드는 항상 표시).
  // 엣지: 위계(하위→대주제 child_of) + belongs_to(콘텐츠→노드) + precedes(학습 순서).
  const graph = useMemo(() => {
    const contentBelongs = new Map<string, string[]>();
    for (const e of data.edges)
      if (e.rel === "belongs_to") {
        const arr = contentBelongs.get(e.source) ?? [];
        arr.push(e.target);
        contentBelongs.set(e.source, arr);
      }
    const isHidden = (n: GraphNode) => {
      if (n.kind !== "content") return false; // 토픽(대주제·auto)은 항상 표시
      const bs = contentBelongs.get(n.id);
      if (!bs || bs.length === 0) return false; // 소속 없는 콘텐츠는 표시(고아 방지)
      return bs.every((t) => collapsed.has(t)); // 소속 노드가 모두 접힘 → 숨김
    };
    const nodes = data.nodes.filter((n) => !isHidden(n)).map((n) => ({ ...n }));
    const shown = new Set(nodes.map((n) => n.id));
    const links: { source: string; target: string; rel: string; weight: number }[] = [];
    for (const n of data.nodes) // 위계: 하위 → 대주제
      if (n.kind === "topic" && n.parent && shown.has(n.id) && shown.has(n.parent))
        links.push({ source: n.id, target: n.parent, rel: "child_of", weight: 0.5 });
    for (const e of data.edges)
      if ((e.rel === "precedes" || e.rel === "belongs_to") && shown.has(e.source) && shown.has(e.target))
        links.push({ source: e.source, target: e.target, rel: e.rel, weight: e.weight });
    return { nodes, links };
  }, [data, collapsed]);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !FG) return;
    fg.d3Force("charge")?.strength((n: any) => (n.kind === "topic" && !n.auto ? -480 : -55));
    const link = fg.d3Force("link");
    if (link) {
      link
        .distance((l: any) => (l.rel === "belongs_to" ? 64 : 36))
        .strength((l: any) => (l.rel === "similar_to" ? 0.04 : 0.45));
    }
    fg.d3Force(
      "collide",
      forceCollide((n: any) => (n.kind === "topic" && !n.auto ? 48 : n.auto ? 10 : 6)).strength(0.9)
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

  useEffect(() => {
    if (!selectedNode) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSelectedNode(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedNode]);

  function handleNodeHover(node: GraphNode | null) {
    hoveredNodeRef.current = node;
    fgRef.current?.refresh?.();
  }

  /**
   * 클릭 라우팅:
   *   대주제(topic, !auto) → /discover?topic=<id>  (모달 없음, early return으로 충돌 방지)
   *   세부 노드(content / auto) → 모달 오픈
   */
  /**
   * 클릭 라우팅:
   *   대주제(topic, !auto) → /discover?topic=<id>  (early return으로 모달 충돌 방지)
   *   세부 노드(content / auto) → 모달 오픈
   * e.stopPropagation/preventDefault로 이벤트 버블링 원천 차단.
   */
  function handleNodeClick(n: GraphNode, e?: MouseEvent) {
    if (e && e.stopPropagation) e.stopPropagation();
    if (e && e.preventDefault) e.preventDefault();

    if (n.kind === "content") {
      setSelectedNode({ id: n.id, label: n.label, kind: n.kind, contentId: parseContentId(n.id) });
      setSelectKey((k) => k + 1);
      return;
    }
    // 대주제·auto 노드 클릭 = 그에 속한 콘텐츠 접기/펴기 토글
    // auto면 자신만, 대주제면 자신 + auto 자식 전부를 한 번에 토글
    setCollapsed((cur) => {
      const next = new Set(cur);
      const targets = n.auto
        ? [n.id]
        : [n.id, ...data.nodes.filter((x) => x.parent === n.id).map((x) => x.id)];
      const anyOpen = targets.some((t) => !next.has(t));
      for (const t of targets) {
        if (anyOpen) next.add(t);
        else next.delete(t);
      }
      return next;
    });
  }

  /**
   * 색상 우선순위: URL-포커스 > 학습경로 > URL-하이라이트 > 기본(호버 활성 시 dim)
   * 호버 앰버/pathHover는 nodeColor가 아닌 nodeCanvasObject(replace 모드)에서 처리.
   * — react-force-graph-2d는 fg.refresh() 시 nodeColor를 재평가하지 않으므로
   *   호버 색상은 refresh마다 확실히 호출되는 nodeCanvasObject에서만 그린다.
   */
  function getNodeColor(n: GraphNode): string {
    if (n.id === highlight?.focusId) return C.urlFocus;
    if (pathIdsSet.has(n.id)) return C.path;
    if (highlightIds.has(n.id)) return C.urlHL;
    const base = n.auto ? NODE_COLORS.auto : (NODE_COLORS[n.kind] ?? NODE_COLORS.content);
    return hoveredNodeRef.current !== null ? hexRgba(base, 0.7) : base;
  }

  function getNodeVal(n: GraphNode): number {
    if (n.id === highlight?.focusId) return n.kind === "topic" ? 11 : 4;
    if (highlightIds.has(n.id)) return n.kind === "topic" ? 10 : 3;
    return baseNodeVal(n);
  }

  /**
   * 툴팁 분기:
   *   학습 경로 내 노드 → "[내 학습 경로] <label>"
   *   그 외        → "[새로운 탐색] <label>"
   */
  function getNodeLabel(n: GraphNode): string {
    const prefix = pathIdsSet.has(n.id) ? "[읽은 글]" : "[새로운 탐색]";
    return `${prefix} ${n.label}`;
  }

  function drawLabel(
    n: GraphNode & { x: number; y: number },
    ctx: CanvasRenderingContext2D,
    scale: number,
    isFocus: boolean
  ) {
    const fs = (n.kind === "topic" ? (n.auto ? 10 : 13) : 9) / scale; // 대주제 13(유지) / 하위 10 / 콘텐츠 9
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
    ctx.fillStyle = isFocus ? C.urlFocusSoft : "rgba(255,255,255,0.92)";
    ctx.fill();
    ctx.fillStyle = "#14161C";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(n.label, n.x, by + padY);
  }

  /**
   * REPLACE 모드 (호버 노드): 기본 원 대신 이 함수가 전체 렌더를 담당.
   *   — fg.refresh() 시 nodeColor는 재평가되지 않지만 nodeCanvasObject는 항상 호출됨.
   *   — 따라서 앰버/pathHover 색상은 반드시 여기서 그려야 즉각 반영된다.
   * AFTER 모드 (경로·토픽·HL 노드): 기본 원 위에 글로우 링 + 라벨을 덧그린다.
   */
  function drawNodeExtras(
    n: GraphNode & { x: number; y: number },
    ctx: CanvasRenderingContext2D,
    scale: number
  ) {
    const isFocus = n.id === highlight?.focusId;
    const isHL = highlightIds.has(n.id);
    const isPath = pathIdsSet.has(n.id);
    const isHovered = hoveredNodeRef.current?.id === n.id;

    // ── REPLACE 모드: 호버 노드 전체 수동 렌더 ─────────────────────────────
    if (isHovered) {
      // 1. 채운 원 (앰버 or 진한 인디고)
      const circleR = Math.sqrt(getNodeVal(n)) * 4 / scale; // nodeRelSize=4
      ctx.beginPath();
      ctx.arc(n.x, n.y, circleR, 0, Math.PI * 2);
      ctx.fillStyle = isPath ? C.pathHover : C.hover;
      ctx.fill();

      // 2. 글로우 링
      const glowR = (n.kind === "topic" ? 20 : 13) / scale;
      ctx.save();
      ctx.shadowColor = isPath ? C.path : C.hover;
      ctx.shadowBlur = (isPath ? 28 : 14) / scale;
      ctx.beginPath();
      ctx.arc(n.x, n.y, glowR, 0, Math.PI * 2);
      ctx.strokeStyle = isPath ? C.pathGlowHover : C.hoverGlow;
      ctx.lineWidth = (isPath ? 3.5 : 2) / scale;
      ctx.stroke();
      ctx.restore();

      // 3. 라벨 (토픽 / 포커스 노드만)
      if ((n.kind === "topic" || isFocus) && n.label) drawLabel(n, ctx, scale, isFocus);
      return;
    }

    // ── AFTER 모드: 비호버 경로·토픽·HL 노드 — 기본 원 위에 덧그리기 ──────

    // 학습 경로 글로우 링 (상시 켜짐)
    if (isPath) {
      const glowR = (n.kind === "topic" ? 20 : 13) / scale;
      ctx.save();
      ctx.shadowColor = C.path;
      ctx.shadowBlur = 18 / scale;
      ctx.beginPath();
      ctx.arc(n.x, n.y, glowR, 0, Math.PI * 2);
      ctx.strokeStyle = C.pathGlow;
      ctx.lineWidth = 2.5 / scale;
      ctx.stroke();
      ctx.restore();
    }

    // URL-하이라이트 링 (포커스 노드는 경로 여부 무관하게 표시)
    if (isHL) {
      const radius = (isFocus ? 16 : 11) / scale;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
      ctx.strokeStyle = isFocus ? "rgba(217,164,65,0.92)" : "rgba(217,164,65,0.7)";
      ctx.lineWidth = (isFocus ? 2.4 : 1.6) / scale;
      ctx.stroke();
    }

    // 라벨 (토픽 노드 상시, 포커스 노드 상시)
    if ((n.kind !== "topic" && !isFocus) || !n.label) return;
    drawLabel(n, ctx, scale, isFocus);
  }

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
          onNodeClick={(n: GraphNode, e: MouseEvent) => handleNodeClick(n, e)}
          onNodeHover={(n: GraphNode | null) => handleNodeHover(n)}
          nodeVal={(n: GraphNode) => getNodeVal(n)}
          nodeColor={(n: GraphNode) => getNodeColor(n)}
          nodeLabel={(n: GraphNode) => getNodeLabel(n)}
          linkColor={(l: GraphLink) => {
            const src = linkNodeId(l.source);
            const tgt = linkNodeId(l.target);
            const anyHover = hoveredNodeRef.current !== null;
            // 추천 경로 — 읽은 콘텐츠에 닿는 precedes 간선을 빨강으로 강조
            if (src && tgt && l.rel === "precedes" && (pathIdsSet.has(src) || pathIdsSet.has(tgt)))
              return anyHover ? "rgba(225,72,59,0.55)" : "rgba(225,72,59,0.82)";
            // 그 외 precedes(학습 순서 구조) — 옅은 빨강
            if (l.rel === "precedes") return "rgba(225,72,59,0.3)";
            // URL-하이라이트 간선
            if (src && tgt && highlightIds.has(src) && highlightIds.has(tgt))
              return "rgba(217,164,65,0.56)";
            // 일반 간선 — 호버 활성 시 dim
            return anyHover ? "rgba(120,132,156,0.07)" : "rgba(120,132,156,0.1)";
          }}
          linkWidth={(l: GraphLink) => {
            const src = linkNodeId(l.source);
            const tgt = linkNodeId(l.target);
            if (src && tgt && l.rel === "precedes" && (pathIdsSet.has(src) || pathIdsSet.has(tgt))) return 2.6;
            if (l.rel === "precedes") return 1.4;
            if (src && tgt && highlightIds.has(src) && highlightIds.has(tgt)) return 2.2;
            return Math.max(0.3, l.weight ?? 0.3);
          }}
          d3VelocityDecay={0.32}
          cooldownTicks={160}
          nodeCanvasObjectMode={(n: GraphNode) => {
            if (hoveredNodeRef.current?.id === n.id) return "replace";
            if (
              n.kind === "topic" ||
              pathIdsSet.has(n.id) ||
              highlightIds.has(n.id)
            ) return "after";
            return undefined;
          }}
          nodeCanvasObject={(
            n: GraphNode & { x: number; y: number },
            ctx: CanvasRenderingContext2D,
            scale: number
          ) => drawNodeExtras(n, ctx, scale)}
        />
      )}

      {selectedNode?.contentId !== undefined && (
        <ReadModal
          key={selectKey}
          contentId={selectedNode.contentId}
          title={selectedNode.label}
          url={null}
          loggedIn={loggedIn}
          renderTrigger={(openFn) => <GraphNodeAutoOpen openFn={openFn} />}
        />
      )}
    </div>
  );
}
