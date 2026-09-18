import { useSyncExternalStore } from "react";
import {
  adaptProcessingGraph,
  type ProcessResponse,
  type ProcessingGraph,
} from "@/lib/processing-api";

export interface LiveProcessingResult {
  response: ProcessResponse;
  graph: ProcessingGraph;
  receivedAt: string;
}

let current: LiveProcessingResult | null = null;
const listeners = new Set<() => void>();

export function setLiveProcessingResult(response: ProcessResponse) {
  current = {
    response,
    graph: adaptProcessingGraph(response),
    receivedAt: new Date().toISOString(),
  };
  listeners.forEach((listener) => listener());
}

export function useLiveProcessingResult() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
    () => null,
  );
}
