import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  EDGES,
  ENTITY_KIND_META,
  NODES,
  type EntityEdge,
  type EntityKind,
  type EntityNode,
} from "@/data/case-data";
import type { ProcessingGraph } from "@/lib/processing-api";
import { cn } from "@/lib/utils";

const W = 1480;
const H = 900;

export interface GraphView {
  selectedNode: string | null;
  selectedEdge: string | null;
}

interface Props {
  graph?: ProcessingGraph;
  visibleKinds: Set<EntityKind>;
  visibleRels: Set<string>;
  minConfidence: number;
  query: string;
  focusSet: string[] | null;
  selectedNode: string | null;
  selectedEdge: string | null;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (id: string | null) => void;
  expanded: Set<string>;
}

function shapePath(node: EntityNode, r: number) {
  const { x, y } = node;
  switch (ENTITY_KIND_META[node.kind].shape) {
    case "square":
      return `M ${x - r} ${y - r} H ${x + r} V ${y + r} H ${x - r} Z`;
    case "diamond":
      return `M ${x} ${y - r * 1.15} L ${x + r * 1.15} ${y} L ${x} ${y + r * 1.15} L ${x - r * 1.15} ${y} Z`;
    case "triangle":
      return `M ${x} ${y - r * 1.2} L ${x + r * 1.15} ${y + r * 0.85} L ${x - r * 1.15} ${y + r * 0.85} Z`;
    case "hex": {
      const pts = Array.from({ length: 6 }, (_, i) => {
        const a = (Math.PI / 3) * i - Math.PI / 6;
        return `${x + r * 1.1 * Math.cos(a)} ${y + r * 1.1 * Math.sin(a)}`;
      });
      return `M ${pts.join(" L ")} Z`;
    }
    default:
      return "";
  }
}

export function NetworkGraph({
  graph,
  visibleKinds,
  visibleRels,
  minConfidence,
  query,
  focusSet,
  selectedNode,
  selectedEdge,
  onSelectNode,
  onSelectEdge,
  expanded,
}: Props) {
  const [transform, setTransform] = useState({ k: 0.56, x: 24, y: 170 });
  const [hover, setHover] = useState<string | null>(null);
  const dragRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const reset = useCallback(() => setTransform({ k: 0.56, x: 24, y: 170 }), []);

  const graphNodes = graph?.nodes ?? NODES;
  const graphEdges = graph?.edges ?? EDGES;
  const nodeMap = useMemo(() => new Map(graphNodes.map((n) => [n.id, n])), [graphNodes]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = graphNodes.filter((n) => {
      if (!visibleKinds.has(n.kind)) return false;
      if ((n.confidence ?? 100) < minConfidence) return false;
      if (focusSet && !focusSet.includes(n.id) && !expanded.has(n.id)) {
        const touchesFocus = graphEdges.some(
          (e) => (expanded.has(e.from) && e.to === n.id) || (expanded.has(e.to) && e.from === n.id),
        );
        if (!touchesFocus) return false;
      }
      return true;
    });
    const ids = new Set(base.map((n) => n.id));
    const matches = q
      ? new Set(
          base
            .filter(
              (n) =>
                n.label.toLowerCase().includes(q) ||
                (n.alias ?? "").toLowerCase().includes(q) ||
                (n.sub ?? "").toLowerCase().includes(q),
            )
            .map((n) => n.id),
        )
      : null;
    return { nodes: base, ids, matches };
  }, [visibleKinds, minConfidence, focusSet, expanded, query, graphNodes, graphEdges]);

  const edges = useMemo(
    () =>
      graphEdges.filter(
        (e) =>
          visibleRels.has(e.kind) &&
          e.confidence >= minConfidence &&
          shown.ids.has(e.from) &&
          shown.ids.has(e.to),
      ),
    [visibleRels, minConfidence, shown.ids, graphEdges],
  );

  const neighborIds = useMemo(() => {
    if (!selectedNode) return null;
    const s = new Set<string>([selectedNode]);
    edges.forEach((e) => {
      if (e.from === selectedNode) s.add(e.to);
      if (e.to === selectedNode) s.add(e.from);
    });
    return s;
  }, [selectedNode, edges]);

  useEffect(() => {
    if (!selectedNode) return;
    const n = nodeMap.get(selectedNode);
    if (!n) return;
    setTransform((t) => {
      const k = Math.max(t.k, 0.85);
      const rect = svgRef.current?.getBoundingClientRect();
      const cw = rect?.width ?? 900;
      const ch = rect?.height ?? 620;
      return { k, x: cw / 2 - n.x * k, y: ch / 2 - n.y * k };
    });
  }, [selectedNode, nodeMap]);

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const rect = svgRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    setTransform((t) => {
      const k = Math.min(2.4, Math.max(0.35, t.k * (e.deltaY < 0 ? 1.12 : 0.89)));
      const ratio = k / t.k;
      return { k, x: mx - (mx - t.x) * ratio, y: my - (my - t.y) * ratio };
    });
  };

  const zoomBy = (f: number) =>
    setTransform((t) => {
      const rect = svgRef.current?.getBoundingClientRect();
      const mx = (rect?.width ?? 900) / 2;
      const my = (rect?.height ?? 600) / 2;
      const k = Math.min(2.4, Math.max(0.35, t.k * f));
      const ratio = k / t.k;
      return { k, x: mx - (mx - t.x) * ratio, y: my - (my - t.y) * ratio };
    });

  const showLabels = transform.k > 0.5;
  const showEdgeLabels = transform.k > 1.0;

  return (
    <div className="relative h-full w-full overflow-hidden bg-background grid-backdrop">
      <svg
        ref={svgRef}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        onWheel={onWheel}
        onPointerDown={(e) => {
          dragRef.current = { x: e.clientX, y: e.clientY, tx: transform.x, ty: transform.y };
          (e.target as Element).setPointerCapture?.(e.pointerId);
        }}
        onPointerMove={(e) => {
          const d = dragRef.current;
          if (!d) return;
          setTransform((t) => ({ ...t, x: d.tx + (e.clientX - d.x), y: d.ty + (e.clientY - d.y) }));
        }}
        onPointerUp={() => (dragRef.current = null)}
        onPointerLeave={() => (dragRef.current = null)}
        onClick={(e) => {
          if (e.target === svgRef.current) {
            onSelectNode(null);
            onSelectEdge(null);
          }
        }}
      >
        <g transform={`translate(${transform.x} ${transform.y}) scale(${transform.k})`}>
          {/* cluster hulls */}
          {["Kochi core", "Finance ring", "Transport", "Mumbai node"].map((c) => {
            const ns = shown.nodes.filter((n) => n.cluster === c);
            if (ns.length < 2) return null;
            const xs = ns.map((n) => n.x);
            const ys = ns.map((n) => n.y);
            const pad = 46;
            const x = Math.min(...xs) - pad;
            const y = Math.min(...ys) - pad;
            return (
              <g key={c}>
                <rect
                  x={x}
                  y={y}
                  width={Math.max(...xs) - Math.min(...xs) + pad * 2}
                  height={Math.max(...ys) - Math.min(...ys) + pad * 2}
                  rx={18}
                  className="fill-foreground/2 stroke-border"
                  strokeDasharray="4 6"
                />
                <text
                  x={x + 12}
                  y={y + 20}
                  className="fill-muted-foreground font-mono"
                  fontSize={11}
                  letterSpacing="1.5"
                >
                  {c.toUpperCase()}
                </text>
              </g>
            );
          })}

          {/* edges */}
          {edges.map((e) => {
            const a = nodeMap.get(e.from)!;
            const b = nodeMap.get(e.to)!;
            const isSel = selectedEdge === e.id;
            const dim =
              (neighborIds && !(neighborIds.has(e.from) && neighborIds.has(e.to))) ||
              (selectedEdge && !isSel);
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            return (
              <g key={e.id} opacity={dim ? 0.13 : 1} className="transition-opacity duration-200">
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  strokeWidth={isSel ? 2.6 : e.suspicious ? 1.9 : 1.1}
                  className={cn(
                    isSel
                      ? "stroke-primary"
                      : e.suspicious
                        ? "stroke-destructive/70"
                        : "stroke-border-strong",
                    e.suspicious && !dim && "edge-flow",
                  )}
                />
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  strokeWidth={14}
                  stroke="transparent"
                  className="cursor-pointer"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    onSelectEdge(e.id);
                    onSelectNode(null);
                  }}
                />
                {(showEdgeLabels || isSel) && (
                  <text
                    x={mx}
                    y={my - 4}
                    textAnchor="middle"
                    fontSize={9}
                    letterSpacing="0.8"
                    className={cn(
                      "pointer-events-none font-mono",
                      isSel
                        ? "fill-primary"
                        : e.suspicious
                          ? "fill-destructive/80"
                          : "fill-muted-foreground",
                    )}
                  >
                    {e.kind}
                    {e.count ? ` ·${e.count}` : ""}
                  </text>
                )}
              </g>
            );
          })}

          {/* nodes */}
          {shown.nodes.map((n) => {
            const meta = ENTITY_KIND_META[n.kind];
            const isSel = selectedNode === n.id;
            const isNeighbor = neighborIds?.has(n.id);
            const isMatch = shown.matches?.has(n.id);
            const dim =
              (neighborIds && !isNeighbor) ||
              (shown.matches && !isMatch) ||
              (selectedEdge != null &&
                !edges.some((e) => e.id === selectedEdge && (e.from === n.id || e.to === n.id)));
            const r = n.kind === "person" ? 15 : 11;
            const isPill = meta.shape === "pill";
            const isCircle = meta.shape === "circle";

            return (
              <g
                key={n.id}
                opacity={dim ? 0.16 : 1}
                className="cursor-pointer transition-opacity duration-200"
                onClick={(ev) => {
                  ev.stopPropagation();
                  onSelectNode(n.id);
                  onSelectEdge(null);
                }}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
              >
                {(isSel || n.alert === "high") && (
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={r + (isSel ? 13 : 9)}
                    fill="none"
                    strokeWidth={1}
                    className={isSel ? "stroke-primary/70" : "stroke-destructive/35"}
                  />
                )}
                {isCircle && (
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={r}
                    style={{
                      fill: `color-mix(in oklab, ${meta.token} 22%, transparent)`,
                      stroke: meta.token,
                    }}
                    strokeWidth={isSel || hover === n.id ? 2.2 : 1.4}
                  />
                )}
                {isPill && (
                  <rect
                    x={n.x - 16}
                    y={n.y - 9}
                    width={32}
                    height={18}
                    rx={9}
                    style={{
                      fill: `color-mix(in oklab, ${meta.token} 20%, transparent)`,
                      stroke: meta.token,
                    }}
                    strokeWidth={isSel || hover === n.id ? 2.2 : 1.4}
                  />
                )}
                {!isCircle && !isPill && (
                  <path
                    d={shapePath(n, r)}
                    style={{
                      fill: `color-mix(in oklab, ${meta.token} 20%, transparent)`,
                      stroke: meta.token,
                    }}
                    strokeWidth={isSel || hover === n.id ? 2.2 : 1.4}
                  />
                )}
                {n.alert === "high" && (
                  <circle cx={n.x + r + 3} cy={n.y - r - 1} r={3} className="fill-destructive" />
                )}
                {(showLabels || isSel || hover === n.id) && (
                  <text
                    x={n.x}
                    y={n.y + r + 14}
                    textAnchor="middle"
                    fontSize={n.kind === "person" ? 11.5 : 10.5}
                    className={cn(
                      "pointer-events-none",
                      isSel ? "fill-foreground" : "fill-foreground/75",
                      n.kind !== "person" && "font-mono",
                    )}
                  >
                    {n.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* zoom controls */}
      <div className="absolute bottom-4 left-4 flex flex-col overflow-hidden rounded-sm border border-border bg-surface">
        {[
          { label: "+", fn: () => zoomBy(1.2) },
          { label: "−", fn: () => zoomBy(0.83) },
          { label: "⤢", fn: reset },
        ].map((b) => (
          <button
            key={b.label}
            type="button"
            onClick={b.fn}
            className="focus-ring h-8 w-8 border-b border-border text-sm text-muted-foreground last:border-b-0 hover:bg-surface-2 hover:text-foreground"
          >
            {b.label}
          </button>
        ))}
      </div>

      {/* mini-map */}
      <div className="absolute bottom-4 right-4 hidden h-[110px] w-[170px] overflow-hidden rounded-sm border border-border bg-surface/90 lg:block">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
          {edges.map((e) => {
            const a = nodeMap.get(e.from)!;
            const b = nodeMap.get(e.to)!;
            return (
              <line
                key={e.id}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className="stroke-border-strong"
                strokeWidth={2}
              />
            );
          })}
          {shown.nodes.map((n) => (
            <circle
              key={n.id}
              cx={n.x}
              cy={n.y}
              r={n.alert === "high" ? 12 : 8}
              style={{ fill: ENTITY_KIND_META[n.kind].token }}
              opacity={n.alert === "high" ? 1 : 0.6}
            />
          ))}
        </svg>
        <div className="pointer-events-none absolute left-1.5 top-1 font-mono text-[9px] tracking-widest text-muted-foreground">
          MINIMAP
        </div>
      </div>

      {/* legend */}
      <div className="absolute left-4 top-4 rounded-sm border border-border bg-surface/95 px-3 py-2.5">
        <div className="label-eyebrow mb-2">Legend</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {(Object.keys(ENTITY_KIND_META) as EntityKind[]).map((k) => (
            <div key={k} className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{
                  background: `color-mix(in oklab, ${ENTITY_KIND_META[k].token} 30%, transparent)`,
                  border: `1px solid ${ENTITY_KIND_META[k].token}`,
                }}
              />
              {ENTITY_KIND_META[k].label}
            </div>
          ))}
          <div className="col-span-2 mt-1 flex items-center gap-2 border-t border-border pt-1.5 text-[11px] text-muted-foreground">
            <span className="h-0 w-5 border-t-2 border-dashed border-destructive/70" />
            Potentially suspicious link
          </div>
        </div>
      </div>

      <div className="pointer-events-none absolute right-4 top-4 font-mono text-[10px] tracking-widest text-muted-foreground">
        {shown.nodes.length} NODES · {edges.length} EDGES · {(transform.k * 100).toFixed(0)}%
      </div>
    </div>
  );
}

export type { EntityEdge, EntityNode };
