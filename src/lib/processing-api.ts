import type { EntityEdge, EntityKind, EntityNode } from "@/data/case-data";

export const SUPPORTED_UPLOAD_EXTENSIONS = new Set([
  "pdf",
  "docx",
  "txt",
  "png",
  "jpg",
  "jpeg",
  "csv",
  "xlsx",
  "json",
]);

export interface SourceLocation {
  page_number?: number | null;
  paragraph_number?: number | null;
  table_number?: number | null;
  line_number?: number | null;
  sheet_name?: string | null;
  row_number?: number | null;
  column_number?: number | null;
  json_path?: string | null;
  character_start?: number | null;
  character_end?: number | null;
  source_path?: string | null;
  image_width?: number | null;
  image_height?: number | null;
  bounding_box?: [number, number][] | null;
}

export interface BackendProvenance {
  document_id: string;
  page_number?: number | null;
  source_location?: string | null;
  evidence_text?: string | null;
  confidence?: number | null;
}

export interface BackendEntity {
  id: string;
  type: string;
  label: string;
  confidence?: number | null;
  provenance: BackendProvenance[];
  attributes: Record<string, unknown>;
}

export interface BackendRelationship {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  type: string;
  confidence?: number | null;
  provenance: BackendProvenance[];
  attributes: Record<string, unknown>;
}

export interface BackendFragment {
  content: string;
  original_value: unknown;
  confidence?: number | null;
  location: SourceLocation;
}

export interface ProcessResponse {
  artifact: { document_id: string; filename: string; content_type: string; size_bytes: number };
  processing: {
    input_format: string;
    mode: "narrative" | "structured";
    ocr_used: boolean;
    docres_used: boolean;
  };
  fragments: BackendFragment[];
  entities: BackendEntity[];
  relationships: BackendRelationship[];
  relation_decisions: unknown[];
}

export class ProcessApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ProcessApiError";
  }
}

const apiBaseUrl = (import.meta.env["VITE_API_BASE_URL"] ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

export async function processArtifact(file: File, signal?: AbortSignal): Promise<ProcessResponse> {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !SUPPORTED_UPLOAD_EXTENSIONS.has(extension)) {
    throw new ProcessApiError(
      "Unsupported file. Select PDF, DOCX, TXT, PNG, JPG, JPEG, CSV, XLSX, or JSON.",
    );
  }
  if (file.size === 0) throw new ProcessApiError("The selected file is empty.");

  const body = new FormData();
  body.append("artifact", file);
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/process`, {
      method: "POST",
      body,
      ...(signal ? { signal } : {}),
    });
  } catch {
    throw new ProcessApiError(
      `Backend is unavailable at ${apiBaseUrl}. Start the FastAPI service and try again.`,
    );
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ProcessApiError(
      payload?.detail ?? `Processing failed (HTTP ${response.status}).`,
      response.status,
    );
  }
  return (await response.json()) as ProcessResponse;
}

const kindFor = (type: string): EntityKind => {
  switch (type.toLowerCase()) {
    case "person":
      return "person";
    case "phone_number":
      return "phone";
    case "account_number":
      return "account";
    case "vehicle":
      return "vehicle";
    case "location":
      return "location";
    case "organization":
      return "organization";
    default:
      return "social";
  }
};

export interface ProcessingGraph {
  nodes: EntityNode[];
  edges: EntityEdge[];
}

export function adaptProcessingGraph(result: ProcessResponse): ProcessingGraph {
  const total = Math.max(result.entities.length, 1);
  const nodes = result.entities.map((entity, index) => {
    const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
    const confidence = Math.round((entity.confidence ?? 1) * 100);
    return {
      id: entity.id,
      kind: kindFor(entity.type),
      label: entity.label,
      sub: entity.type.replaceAll("_", " "),
      confidence,
      alert: "none" as const,
      cluster: "Uploaded evidence",
      x: 740 + Math.cos(angle) * Math.min(330, 70 + total * 8),
      y: 450 + Math.sin(angle) * Math.min(250, 70 + total * 6),
      sources: [result.artifact.filename],
    } satisfies EntityNode;
  });
  const entityIds = new Set(nodes.map((node) => node.id));
  const edges = result.relationships
    .filter((relationship) => relationship.type !== "NO_RELATION")
    .filter(
      (relationship) =>
        entityIds.has(relationship.source_entity_id) &&
        entityIds.has(relationship.target_entity_id),
    )
    .map((relationship) => ({
      id: relationship.id,
      from: relationship.source_entity_id,
      to: relationship.target_entity_id,
      kind: relationship.type as EntityEdge["kind"],
      confidence: Math.round((relationship.confidence ?? 1) * 100),
      detail:
        relationship.provenance[0]?.evidence_text ??
        "Source evidence available in the uploaded artifact.",
      source: result.artifact.filename,
    }));
  return { nodes, edges };
}

export function parseSourceLocation(provenance?: BackendProvenance): SourceLocation | null {
  if (!provenance?.source_location) return null;
  try {
    return JSON.parse(provenance.source_location) as SourceLocation;
  } catch {
    return null;
  }
}
