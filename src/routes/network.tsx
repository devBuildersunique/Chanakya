import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Crosshair, Info, Layers, RotateCcw, Search, Sparkles, Target, X } from "lucide-react";
import { AppShell } from "@/components/app/AppShell";
import { Chip, Confidence, EvidenceLink, EvidenceViewer, SeverityTag } from "@/components/app/bits";
import { NetworkGraph } from "@/components/app/NetworkGraph";
import { useLiveProcessingResult } from "@/lib/processing-state";
import {
  EDGES,
  ENTITY_KIND_META,
  FLAG_EXPLANATIONS,
  NODES,
  PATTERNS,
  REL_KINDS,
  type EntityKind,
} from "@/data/case-data";

export const Route = createFileRoute("/network")({
  validateSearch: (search: Record<string, unknown>): { pattern?: string; node?: string } => {
    const out: { pattern?: string; node?: string } = {};
    if (typeof search["pattern"] === "string") out.pattern = search["pattern"];
    if (typeof search["node"] === "string") out.node = search["node"];
    return out;
  },
  head: () => ({
    meta: [
      { title: "Investigation Network — Chanakya" },
      {
        name: "description",
        content:
          "Interactive criminal network graph correlating people, phones, accounts, vehicles, locations and organisations from multiple evidence sources.",
      },
      { property: "og:title", content: "Investigation Network — Chanakya" },
      {
        property: "og:description",
        content:
          "Explore entities, relationships and flagged clusters in the unified investigation graph.",
      },
    ],
  }),
  component: Network,
});

const ALL_KINDS = Object.keys(ENTITY_KIND_META) as EntityKind[];

function Network() {
  const { pattern, node } = Route.useSearch();
  const navigate = useNavigate();
  const live = useLiveProcessingResult();
  const liveGraph = live?.graph;
  const graphNodes = liveGraph?.nodes ?? NODES;
  const graphEdges = liveGraph?.edges ?? EDGES;

  const [kinds, setKinds] = useState<Set<EntityKind>>(new Set(ALL_KINDS));
  const [rels, setRels] = useState<Set<string>>(new Set(REL_KINDS));
  const [minConf, setMinConf] = useState(30);
  const [query, setQuery] = useState("");
  const [selectedNode, setSelectedNode] = useState<string | null>(node ?? null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [showWhy, setShowWhy] = useState(false);
  const [note, setNote] = useState("");

  const activePattern = PATTERNS.find((p) => p.id === pattern) ?? null;
  const focusSet = activePattern ? activePattern.focus : null;

  const toggle = <T,>(set: Set<T>, v: T, apply: (s: Set<T>) => void) => {
    const next = new Set(set);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    apply(next);
  };

  const nodeData = selectedNode
    ? (graphNodes.find((item) => item.id === selectedNode) ?? null)
    : null;
  const edgeData = selectedEdge
    ? (graphEdges.find((item) => item.id === selectedEdge) ?? null)
    : null;
  const explanation = selectedNode ? FLAG_EXPLANATIONS[selectedNode] : undefined;

  const neighborStats = useMemo(() => {
    if (!selectedNode) return null;
    const ids = graphEdges
      .filter((e) => e.from === selectedNode || e.to === selectedNode)
      .map((e) => (e.from === selectedNode ? e.to : e.from));
    const counts: Partial<Record<EntityKind, number>> = {};
    ids.forEach((id) => {
      const n = graphNodes.find((item) => item.id === id);
      if (n) counts[n.kind] = (counts[n.kind] ?? 0) + 1;
    });
    return counts;
  }, [selectedNode, graphEdges, graphNodes]);

  useMemo(() => {
    if (liveGraph) setRels(new Set(liveGraph.edges.map((edge) => edge.kind)));
  }, [liveGraph]);

  return (
    <AppShell padded={false}>
      <div className="flex h-full min-h-0">
        {/* LEFT — filters */}
        <aside className="hidden w-[240px] shrink-0 flex-col overflow-y-auto border-r border-border bg-surface lg:flex">
          <div className="border-b border-border px-4 py-3">
            <div className="label-eyebrow">Filter Network</div>
          </div>

          <div className="space-y-5 px-4 py-4">
            <div className="relative">
              <Search
                className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground"
                strokeWidth={1.75}
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search within graph…"
                className="focus-ring w-full rounded-sm border border-input bg-background py-2 pl-8 pr-2 text-[12.5px] placeholder:text-muted-foreground/70"
              />
            </div>

            <FilterGroup title="Entity Type">
              {ALL_KINDS.map((k) => (
                <CheckRow
                  key={k}
                  checked={kinds.has(k)}
                  onChange={() => toggle(kinds, k, setKinds)}
                  label={ENTITY_KIND_META[k].label}
                  dot={ENTITY_KIND_META[k].token}
                  count={graphNodes.filter((n) => n.kind === k).length}
                />
              ))}
            </FilterGroup>

            <FilterGroup title="Relationship">
              {REL_KINDS.map((r) => (
                <CheckRow
                  key={r}
                  checked={rels.has(r)}
                  onChange={() => toggle(rels, r, setRels)}
                  label={r}
                  count={graphEdges.filter((e) => e.kind === r).length}
                  mono
                />
              ))}
            </FilterGroup>

            <div>
              <div className="label-eyebrow mb-2">Minimum Confidence</div>
              <input
                type="range"
                min={0}
                max={95}
                value={minConf}
                onChange={(e) => setMinConf(Number(e.target.value))}
                className="w-full accent-primary"
              />
              <div className="mt-1 flex justify-between font-mono text-[10.5px] text-muted-foreground">
                <span>0%</span>
                <span className="text-foreground">{minConf}%</span>
                <span>95%</span>
              </div>
            </div>

            <div>
              <div className="label-eyebrow mb-2">Date Range</div>
              <select className="focus-ring w-full rounded-sm border border-input bg-background px-2 py-1.5 text-[12.5px]">
                <option>04 Aug – 20 Aug 2026</option>
                <option>Last 7 days</option>
                <option>Full case history</option>
              </select>
            </div>

            <div>
              <div className="label-eyebrow mb-2">Source</div>
              <select className="focus-ring w-full rounded-sm border border-input bg-background px-2 py-1.5 text-[12.5px]">
                <option>All sources</option>
                <option>FIR only</option>
                <option>CDR only</option>
                <option>Financial only</option>
                <option>Surveillance only</option>
                <option>Social intelligence only</option>
              </select>
            </div>

            <div>
              <div className="label-eyebrow mb-2">Alert Level</div>
              <div className="flex gap-1.5">
                {["High", "Medium", "Low"].map((a) => (
                  <span
                    key={a}
                    className="rounded-sm border border-border px-2 py-1 text-[11px] text-muted-foreground"
                  >
                    {a}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                className="focus-ring flex-1 rounded-sm bg-primary px-3 py-1.5 text-[12.5px] font-medium text-primary-foreground hover:opacity-90"
              >
                Apply
              </button>
              <button
                type="button"
                onClick={() => {
                  setKinds(new Set(ALL_KINDS));
                  setRels(new Set(REL_KINDS));
                  setMinConf(30);
                  setQuery("");
                  setExpanded(new Set());
                  navigate({ to: "/network", search: {} });
                }}
                className="focus-ring rounded-sm border border-border px-3 py-1.5 text-[12.5px] text-foreground hover:bg-surface-2"
              >
                <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
              </button>
            </div>
          </div>

          <div className="mt-auto border-t border-border px-4 py-3">
            <div className="label-eyebrow mb-2">Focus Investigation</div>
            <div className="space-y-1.5">
              {PATTERNS.slice(0, 3).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => navigate({ to: "/network", search: { pattern: p.id } })}
                  className={`focus-ring flex w-full items-center gap-2 rounded-sm border px-2 py-1.5 text-left text-[11.5px] transition-colors ${
                    activePattern?.id === p.id
                      ? "border-primary/50 bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:bg-surface-2"
                  }`}
                >
                  <Target className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                  <span className="truncate">{p.name}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* CENTER — graph */}
        <div className="relative flex min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-2">
            <Layers className="h-4 w-4 text-primary" strokeWidth={1.75} />
            <span className="text-[13px] font-medium text-foreground">Investigation Network</span>
            {activePattern && (
              <span className="flex items-center gap-2 rounded-sm border border-primary/40 bg-primary/10 px-2 py-1 text-[11.5px] text-primary">
                <Crosshair className="h-3.5 w-3.5" strokeWidth={1.75} />
                Focused: {activePattern.name}
                <button type="button" onClick={() => navigate({ to: "/network", search: {} })}>
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
            <span className="ml-auto flex items-center gap-1.5 text-[11px] text-warning">
              <Info className="h-3.5 w-3.5" strokeWidth={1.75} />
              AI analysis supports investigators. Findings require human verification.
            </span>
          </div>

          <div className="min-h-0 flex-1">
            <NetworkGraph
              {...(liveGraph ? { graph: liveGraph } : {})}
              visibleKinds={kinds}
              visibleRels={rels}
              minConfidence={minConf}
              query={query}
              focusSet={focusSet}
              selectedNode={selectedNode}
              selectedEdge={selectedEdge}
              onSelectNode={(id) => {
                setSelectedNode(id);
                setShowWhy(false);
              }}
              onSelectEdge={setSelectedEdge}
              expanded={expanded}
            />
          </div>
        </div>

        {/* RIGHT — detail panel */}
        <aside className="hidden w-[330px] shrink-0 flex-col overflow-y-auto border-l border-border bg-surface xl:flex">
          {!nodeData && !edgeData && (
            <div className="px-5 py-6">
              <div className="label-eyebrow mb-3">Selection</div>
              <p className="text-[12.5px] leading-relaxed text-muted-foreground">
                Select a node to inspect an entity, its identifiers, network reach and supporting
                sources. Select an edge to inspect a relationship and the record it came from.
              </p>
              <div className="mt-5 space-y-2">
                <div className="label-eyebrow">Network summary</div>
                {[
                  ["Entities", graphNodes.length],
                  ["Relationships", graphEdges.length],
                  ["Potentially suspicious links", graphEdges.filter((e) => e.suspicious).length],
                  ["High-alert entities", graphNodes.filter((n) => n.alert === "high").length],
                ].map(([l, v]) => (
                  <div
                    key={l as string}
                    className="flex justify-between border-b border-border py-1.5 text-[12.5px]"
                  >
                    <span className="text-muted-foreground">{l as string}</span>
                    <span className="font-mono tabular-nums text-foreground">{v as number}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {edgeData && (
            <div className="px-5 py-5">
              <div className="label-eyebrow">Relationship</div>
              <div className="mt-2 font-mono text-sm text-primary">{edgeData.kind}</div>
              <div className="mt-3 space-y-1.5 text-[13px]">
                <div className="text-foreground">
                  {graphNodes.find((item) => item.id === edgeData.from)?.label}
                </div>
                <div className="text-muted-foreground">↓</div>
                <div className="text-foreground">
                  {graphNodes.find((item) => item.id === edgeData.to)?.label}
                </div>
              </div>
              <div className="mt-4 space-y-3">
                <div>
                  <div className="label-eyebrow mb-1">Confidence</div>
                  <Confidence value={edgeData.confidence} />
                </div>
                {edgeData.count && (
                  <div className="flex justify-between text-[12.5px]">
                    <span className="text-muted-foreground">Observed events</span>
                    <span className="font-mono text-foreground">{edgeData.count}</span>
                  </div>
                )}
                <p className="rounded-sm border border-border bg-background px-3 py-2 text-[12.5px] leading-relaxed text-foreground/90">
                  {edgeData.detail}
                </p>
                {edgeData.suspicious && <SeverityTag level="high" />}
                <div>
                  <div className="label-eyebrow mb-1.5">Source record</div>
                  <EvidenceLink id={edgeData.source} onOpen={setEvidenceId} />
                </div>
              </div>
            </div>
          )}

          {nodeData && !showWhy && (
            <div className="px-5 py-5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="label-eyebrow">{ENTITY_KIND_META[nodeData.kind].label}</div>
                  <h2 className="mt-1 text-[16px] font-semibold text-foreground">
                    {nodeData.label}
                  </h2>
                  {nodeData.alias && (
                    <div className="text-[12px] text-muted-foreground">Alias: {nodeData.alias}</div>
                  )}
                  {nodeData.sub && (
                    <div className="text-[12px] text-muted-foreground">{nodeData.sub}</div>
                  )}
                </div>
                {nodeData.alert !== "none" && <SeverityTag level={nodeData.alert} />}
              </div>

              {nodeData.role && (
                <div className="mt-4 rounded-sm border border-border bg-background px-3 py-2.5">
                  <div className="label-eyebrow">Possible role · AI-derived</div>
                  <div className="mt-1 text-[13.5px] text-foreground">{nodeData.role}</div>
                  {nodeData.confidence != null && (
                    <div className="mt-2">
                      <Confidence value={nodeData.confidence} />
                    </div>
                  )}
                  {explanation && (
                    <button
                      type="button"
                      onClick={() => setShowWhy(true)}
                      className="focus-ring mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-sm border border-warning/40 bg-warning/10 px-2.5 py-1.5 text-[12px] text-warning hover:bg-warning/15"
                    >
                      <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} />
                      Why was this entity flagged?
                    </button>
                  )}
                </div>
              )}

              {nodeData.identifiers && (
                <div className="mt-4">
                  <div className="label-eyebrow mb-2">Identifiers</div>
                  <dl className="space-y-1.5">
                    {nodeData.identifiers.map((idf) => (
                      <div
                        key={idf.label}
                        className="flex justify-between border-b border-border pb-1.5 text-[12.5px]"
                      >
                        <dt className="text-muted-foreground">{idf.label}</dt>
                        <dd className="font-mono text-foreground">{idf.value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}

              {neighborStats && (
                <div className="mt-4">
                  <div className="label-eyebrow mb-2">Network</div>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(neighborStats).map(([k, v]) => (
                      <Chip key={k}>
                        {v} {ENTITY_KIND_META[k as EntityKind].label.toLowerCase()}
                        {v > 1 ? "s" : ""}
                      </Chip>
                    ))}
                  </div>
                </div>
              )}

              <div className="mt-4">
                <div className="label-eyebrow mb-2">Sources</div>
                <div className="space-y-1.5">
                  {nodeData.sources.map((s) => (
                    <EvidenceLink key={s} id={s} onOpen={setEvidenceId} />
                  ))}
                </div>
              </div>

              <div className="mt-5 space-y-2">
                <button
                  type="button"
                  onClick={() => nodeData.sources[0] && setEvidenceId(nodeData.sources[0])}
                  className="focus-ring w-full rounded-sm border border-border px-3 py-2 text-[12.5px] text-foreground hover:bg-surface-2"
                >
                  View Evidence
                </button>
                <button
                  type="button"
                  onClick={() => setExpanded(new Set([...expanded, nodeData.id]))}
                  className="focus-ring w-full rounded-sm border border-border px-3 py-2 text-[12.5px] text-foreground hover:bg-surface-2"
                >
                  Expand Network
                </button>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Add investigation note…"
                  className="focus-ring min-h-16 w-full resize-y rounded-sm border border-input bg-background px-3 py-2 text-[12.5px] placeholder:text-muted-foreground/70"
                />
              </div>

              <Link
                to="/timeline"
                className="mt-4 inline-block text-[12px] text-primary hover:underline"
              >
                View related timeline events →
              </Link>
            </div>
          )}

          {nodeData && showWhy && explanation && (
            <div className="px-5 py-5">
              <button
                type="button"
                onClick={() => setShowWhy(false)}
                className="focus-ring mb-3 text-[12px] text-muted-foreground hover:text-foreground"
              >
                ← Back to entity
              </button>
              <div className="label-eyebrow text-warning">Why this entity was flagged</div>
              <h2 className="mt-2 text-[16px] font-semibold text-foreground">{nodeData.label}</h2>

              <div className="mt-4 rounded-sm border border-warning/30 bg-warning/8 px-3 py-2.5">
                <div className="label-eyebrow text-warning">
                  Possible role · AI-derived interpretation
                </div>
                <div className="mt-1 font-mono text-[15px] tracking-wide text-warning">
                  {explanation.role}
                </div>
                <div className="mt-2">
                  <Confidence value={explanation.confidence} />
                </div>
              </div>

              <div className="mt-4">
                <div className="label-eyebrow mb-2">Supporting signals</div>
                <ul className="space-y-2">
                  {explanation.signals.map((s) => (
                    <li
                      key={s}
                      className="flex gap-2 text-[12.5px] leading-relaxed text-foreground/90"
                    >
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-warning" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="mt-4">
                <div className="label-eyebrow mb-2">Source evidence · raw records</div>
                <div className="space-y-1.5">
                  {explanation.evidence.map((e) => (
                    <EvidenceLink key={e.id} id={e.id} label={e.label} onOpen={setEvidenceId} />
                  ))}
                </div>
              </div>

              <p className="mt-4 rounded-sm border border-border bg-background px-3 py-2 text-[11.5px] leading-relaxed text-muted-foreground">
                AI-generated analysis is investigative assistance and not a determination of guilt.
                All findings require corroboration by the investigating officer.
              </p>
            </div>
          )}
        </aside>
      </div>

      <EvidenceViewer id={evidenceId} onClose={() => setEvidenceId(null)} />
    </AppShell>
  );
}

function FilterGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="label-eyebrow mb-2">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function CheckRow({
  checked,
  onChange,
  label,
  count,
  dot,
  mono,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  count: number;
  dot?: string;
  mono?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 py-0.5 text-[12.5px] text-muted-foreground hover:text-foreground">
      <input type="checkbox" checked={checked} onChange={onChange} className="accent-primary" />
      {dot && (
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{
            background: `color-mix(in oklab, ${dot} 40%, transparent)`,
            border: `1px solid ${dot}`,
          }}
        />
      )}
      <span className={`flex-1 truncate ${mono ? "font-mono text-[11px]" : ""}`}>{label}</span>
      <span className="font-mono text-[10.5px] tabular-nums text-muted-foreground/70">{count}</span>
    </label>
  );
}
