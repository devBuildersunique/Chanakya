import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Check, Circle, CircleDot } from "lucide-react";
import { AppShell, PageHeader, AiNotice } from "@/components/app/AppShell";
import { Chip } from "@/components/app/bits";
import { parseSourceLocation } from "@/lib/processing-api";
import { useLiveProcessingResult } from "@/lib/processing-state";

export const Route = createFileRoute("/processing")({ component: Processing });
const STEPS = [
  "Documents ingested",
  "Text extracted",
  "Entities extracted",
  "Relationships identified",
  "Graph-ready output prepared",
];

function Processing() {
  const navigate = useNavigate();
  const live = useLiveProcessingResult();
  if (!live)
    return (
      <AppShell>
        <PageHeader
          eyebrow="Case · OP-2026-001"
          title="Processing Evidence"
          description="No real upload has been processed in this browser session."
        />
        <section className="panel p-5">
          <p className="text-[13px] text-muted-foreground">
            Select an evidence file first. Mock case data remains unchanged outside the live-upload
            flow.
          </p>
          <Link
            to="/evidence"
            className="mt-4 inline-block text-[12px] text-primary hover:underline"
          >
            Go to evidence upload →
          </Link>
        </section>
      </AppShell>
    );
  const { response } = live;
  const empty = response.entities.length === 0 && response.relationships.length === 0;
  return (
    <AppShell>
      <PageHeader
        eyebrow={`Artifact · ${response.artifact.filename}`}
        title="Processing Evidence"
        description="Live backend processing result from the uploaded artifact."
        actions={<Chip tone="ok">PIPELINE COMPLETE</Chip>}
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_1fr]">
        <section className="panel p-5">
          <div className="label-eyebrow mb-4">Extraction Pipeline</div>
          <ol className="relative space-y-1">
            <span className="absolute bottom-3 left-[9px] top-3 w-px bg-border" />
            {STEPS.map((step) => (
              <li key={step} className="relative flex items-center gap-3 py-1.5">
                <span className="relative z-10 flex h-[19px] w-[19px] items-center justify-center rounded-full bg-surface">
                  <Check className="h-4 w-4 text-success" strokeWidth={2.5} />
                </span>
                <span className="text-[13px] text-foreground/85">{step}</span>
              </li>
            ))}
          </ol>
        </section>
        <div className="space-y-4">
          <section className="panel p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="label-eyebrow">Live Processing Statistics</div>
                <div className="mt-1 text-[12px] text-muted-foreground">
                  {response.processing.mode} · {response.processing.input_format.toUpperCase()} ·
                  OCR {response.processing.ocr_used ? "used" : "not used"}
                </div>
              </div>
              <Chip tone={response.processing.ocr_used ? "warn" : "info"}>
                {response.processing.ocr_used ? "OCR used" : "Native/structured"}
              </Chip>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-3">
              {[
                ["Fragments", response.fragments.length],
                ["Entities", response.entities.length],
                ["Relationships", response.relationships.length],
                ["Relation decisions", response.relation_decisions.length],
                ["Processing", "Complete"],
                ["Result", empty ? "Empty" : "Ready"],
              ].map(([label, value]) => (
                <div key={String(label)} className="bg-surface px-3.5 py-3">
                  <dt className="label-eyebrow">{String(label)}</dt>
                  <dd className="mt-1 font-mono text-xl tabular-nums text-foreground">
                    {String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="panel p-5">
            <div className="label-eyebrow mb-3">Accepted relationships</div>
            {response.relationships.length === 0 ? (
              <p className="text-[12.5px] text-muted-foreground">
                No accepted relationship edges were returned for this artifact.
              </p>
            ) : (
              <div className="space-y-2">
                {response.relationships.map((relationship) => {
                  const source =
                    response.entities.find((entity) => entity.id === relationship.source_entity_id)
                      ?.label ?? relationship.source_entity_id;
                  const target =
                    response.entities.find((entity) => entity.id === relationship.target_entity_id)
                      ?.label ?? relationship.target_entity_id;
                  const location = parseSourceLocation(relationship.provenance[0]);
                  return (
                    <div
                      key={relationship.id}
                      className="rounded-sm border border-border bg-background px-3 py-2"
                    >
                      <div className="font-mono text-[12px] text-primary">
                        {source} → {relationship.type} → {target}
                      </div>
                      <div className="mt-1 text-[11.5px] text-muted-foreground">
                        Confidence {((relationship.confidence ?? 0) * 100).toFixed(1)}%
                        {location?.page_number ? ` · page ${location.page_number}` : ""}
                        {location?.row_number ? ` · row ${location.row_number}` : ""}
                      </div>
                      <div className="mt-1 text-[12px] text-foreground/85">
                        {relationship.provenance[0]?.evidence_text}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
          <AiNotice />
          <div className="flex justify-end pb-2">
            <button
              type="button"
              onClick={() => navigate({ to: "/network" })}
              className="focus-ring rounded-sm bg-primary px-4 py-2 text-[13px] font-medium text-primary-foreground"
            >
              Enter Investigation Workspace
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
