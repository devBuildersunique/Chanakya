import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import {
  Building2,
  Database,
  Eye,
  FileText,
  Globe,
  Lock,
  Phone,
  Upload,
  UploadCloud,
  type LucideIcon,
} from "lucide-react";
import { AppShell, PageHeader } from "@/components/app/AppShell";
import { Chip } from "@/components/app/bits";
import { processArtifact, ProcessApiError, type SourceLocation } from "@/lib/processing-api";
import { setLiveProcessingResult, useLiveProcessingResult } from "@/lib/processing-state";

export const Route = createFileRoute("/evidence")({ component: Evidence });

const SOURCES: { icon: LucideIcon; name: string; desc: string; formats: string }[] = [
  {
    icon: FileText,
    name: "FIR / Police Report",
    desc: "First information reports, case diaries and witness statements.",
    formats: "PDF, DOCX, TXT",
  },
  {
    icon: Phone,
    name: "Call Detail Records",
    desc: "Operator CDR exports with deterministic communication links.",
    formats: "CSV, XLSX",
  },
  {
    icon: Building2,
    name: "Financial Transactions",
    desc: "Bank statement extracts and transfer logs.",
    formats: "CSV, XLSX",
  },
  {
    icon: Database,
    name: "Criminal History",
    desc: "Prior records and antecedent data retained as source evidence.",
    formats: "CSV, JSON",
  },
  {
    icon: Eye,
    name: "Surveillance Reports",
    desc: "Officer observation logs and image-based reports.",
    formats: "PDF, TXT, PNG, JPG",
  },
  {
    icon: Globe,
    name: "Social Media Intelligence",
    desc: "Open-source profile and posting data.",
    formats: "JSON, CSV, TXT",
  },
];

function Evidence() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const live = useLiveProcessingResult();
  const [selected, setSelected] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const choose = (file?: File) => {
    if (file) {
      setSelected(file);
      setStatus("idle");
      setError(null);
    }
  };
  const upload = async () => {
    if (!selected) return inputRef.current?.click();
    setStatus("uploading");
    setError(null);
    try {
      setLiveProcessingResult(await processArtifact(selected));
      setStatus("success");
    } catch (reason) {
      setStatus("error");
      setError(reason instanceof ProcessApiError ? reason.message : "Unexpected upload error.");
    }
  };
  const response = live?.response;
  return (
    <AppShell>
      <PageHeader
        eyebrow="Case · OP-2026-001"
        title="Evidence & Data Ingestion"
        description="Upload one evidence artifact for source-aware processing and graph-ready output."
        actions={
          response ? (
            <Chip tone="ok">
              {response.entities.length} entities · {response.relationships.length} relationships
            </Chip>
          ) : undefined
        }
      />
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {SOURCES.map((source) => (
          <div key={source.name} className="panel flex flex-col p-4">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-2">
                <source.icon className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-[13.5px] font-medium text-foreground">{source.name}</div>
                <div className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
                  {source.desc}
                </div>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
              <span className="font-mono text-[10.5px] tracking-wider text-muted-foreground">
                {source.formats}
              </span>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="focus-ring inline-flex items-center gap-1.5 rounded-sm border border-border px-2.5 py-1.5 text-[12px] hover:border-primary/50 hover:bg-primary/10"
              >
                <Upload className="h-3.5 w-3.5" /> Upload
              </button>
            </div>
          </div>
        ))}
      </div>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.csv,.xlsx,.json"
        onChange={(event: ChangeEvent<HTMLInputElement>) => choose(event.target.files?.[0])}
      />
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event: DragEvent<HTMLDivElement>) => {
          event.preventDefault();
          setDragging(false);
          choose(event.dataTransfer.files[0]);
        }}
        onClick={() => inputRef.current?.click()}
        className={`mt-4 flex cursor-pointer flex-col items-center justify-center rounded-sm border border-dashed px-6 py-8 text-center ${dragging ? "border-primary bg-primary/8" : "border-border-strong bg-surface/50"}`}
      >
        <UploadCloud className="h-6 w-6 text-muted-foreground" />
        <div className="mt-2 text-[13px] text-foreground">Drop evidence file here to upload</div>
        <div className="mt-1 text-[11.5px] text-muted-foreground">
          PDF, DOCX, TXT, PNG/JPG, CSV, XLSX, JSON · backend limit: 25 MB
        </div>
      </div>
      <section className="panel mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="label-eyebrow">Live upload</div>
          {selected && (
            <span className="font-mono text-[11px] text-muted-foreground">{selected.name}</span>
          )}
        </div>
        <div className="space-y-3 px-4 py-4">
          {selected ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-border bg-surface-2/40 px-3 py-2.5">
              <div>
                <div className="font-mono text-[12px] text-foreground">{selected.name}</div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {(selected.size / 1024 / 1024).toFixed(2)} MB
                </div>
              </div>
              <Chip
                tone={
                  status === "success"
                    ? "ok"
                    : status === "error"
                      ? "risk"
                      : status === "uploading"
                        ? "info"
                        : "neutral"
                }
              >
                {status === "uploading"
                  ? "Processing…"
                  : status === "success"
                    ? "Complete"
                    : status === "error"
                      ? "Error"
                      : "Ready to upload"}
              </Chip>
            </div>
          ) : (
            <p className="text-[12.5px] text-muted-foreground">
              Choose a local file to begin a real upload.
            </p>
          )}
          {error && (
            <p
              role="alert"
              className="rounded-sm border border-destructive/35 bg-destructive/10 px-3 py-2 text-[12px] text-destructive"
            >
              {error}
            </p>
          )}
          <button
            type="button"
            disabled={status === "uploading"}
            onClick={upload}
            className="focus-ring rounded-sm bg-primary px-4 py-2 text-[13px] font-medium text-primary-foreground disabled:opacity-50"
          >
            {status === "uploading"
              ? "Processing evidence…"
              : selected
                ? "Upload & Process"
                : "Choose evidence file"}
          </button>
        </div>
      </section>
      {response && (
        <section className="panel mt-6 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div>
              <div className="label-eyebrow">Processed evidence</div>
              <div className="mt-1 font-mono text-[12px] text-primary">
                {response.artifact.filename}
              </div>
            </div>
            <div className="flex gap-2">
              <Chip tone="info">{response.processing.mode}</Chip>
              <Chip tone={response.processing.ocr_used ? "warn" : "neutral"}>
                OCR {response.processing.ocr_used ? "used" : "not used"}
              </Chip>
            </div>
          </div>
          <div className="space-y-3 px-4 py-4">
            <div className="grid gap-2 sm:grid-cols-3">
              <Stat label="Fragments" value={response.fragments.length} />
              <Stat label="Entities" value={response.entities.length} />
              <Stat label="Accepted relationships" value={response.relationships.length} />
            </div>
            <div className="max-h-72 space-y-2 overflow-auto">
              {response.fragments.map((fragment, index) => (
                <div
                  key={`${fragment.content}-${index}`}
                  className="rounded-sm border border-border bg-background px-3 py-2"
                >
                  <div className="text-[12.5px] leading-relaxed text-foreground">
                    {fragment.content || String(fragment.original_value)}
                  </div>
                  <div className="mt-1 font-mono text-[10.5px] text-muted-foreground">
                    {locationText(fragment.location)}
                    {fragment.confidence != null
                      ? ` · OCR confidence ${(fragment.confidence * 100).toFixed(1)}%`
                      : ""}
                    {fragment.location.bounding_box
                      ? ` · OCR polygon ${fragment.location.bounding_box.length} points`
                      : ""}
                  </div>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => navigate({ to: "/processing" })}
              className="focus-ring rounded-sm border border-primary/40 bg-primary/10 px-3 py-1.5 text-[12px] text-primary"
            >
              View processing result →
            </button>
          </div>
        </section>
      )}
      <div className="mt-4 flex items-center gap-2 pb-2 text-[11.5px] text-muted-foreground">
        <Lock className="h-3.5 w-3.5" /> Case data is restricted to authorized investigators.
      </div>
    </AppShell>
  );
}
function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-sm border border-border bg-background px-3 py-2">
      <div className="label-eyebrow">{label}</div>
      <div className="mt-1 font-mono text-lg text-foreground">{value}</div>
    </div>
  );
}
function locationText(location: SourceLocation) {
  const labels: string[] = [];
  const pairs: [keyof SourceLocation, string][] = [
    ["page_number", "page"],
    ["line_number", "line"],
    ["paragraph_number", "paragraph"],
    ["table_number", "table"],
    ["sheet_name", "sheet"],
    ["row_number", "row"],
    ["column_number", "column"],
    ["json_path", "JSON path"],
  ];
  for (const [key, label] of pairs)
    if (location[key] != null) labels.push(`${label}: ${String(location[key])}`);
  return labels.join(" · ") || "Source location not supplied";
}
