import { SSE_EVENT_TYPES, type SSEEvent } from "../types/schemas";
import { api } from "./client";

export interface StreamHandle {
  close: () => void;
}

/** Open an SSE connection for a given audit and dispatch each typed event. */
export function subscribeAudit(
  auditId: string,
  onEvent: (ev: SSEEvent) => void,
  onError?: (err: Event) => void,
): StreamHandle {
  const src = new EventSource(api.streamUrl(auditId));

  const parse = (e: MessageEvent): SSEEvent | null => {
    try {
      return JSON.parse(e.data) as SSEEvent;
    } catch {
      return null;
    }
  };

  for (const type of SSE_EVENT_TYPES) {
    src.addEventListener(type, (e) => {
      const parsed = parse(e as MessageEvent);
      if (parsed) onEvent(parsed);
    });
  }

  src.onerror = (e) => {
    if (onError) onError(e);
  };

  return { close: () => src.close() };
}
