/**
 * Cascade API Service
 * Wraps the /api/cascade/* endpoints.
 *
 * Two chat backends exist side by side (see backend/app/ai/graph/api.py):
 *   /api/cascade/chat          — legacy single-tool-per-turn agent
 *   /api/cascade/graph/chat    — production multi-agent LangGraph
 *                                 orchestrator (Router -> Planner ->
 *                                 [Insight/Goal/Knowledge/Trace/Advisor]
 *                                 -> Formatter), with full explainability
 *                                 (execution_plan, node_trace, evidence,
 *                                 confidence) and the SAME deterministic
 *                                 grounding validator as the legacy path.
 *
 * Toggle which one the UI talks to via VITE_USE_GRAPH_CASCADE=true — no
 * other code changes needed, since both endpoints share the same request
 * shape and a superset response shape.
 */
const USE_GRAPH_ORCHESTRATOR = import.meta.env?.VITE_USE_GRAPH_CASCADE === 'true';

const BASE = '/api/cascade';                 // ingest/health always live here
const CHAT_BASE = USE_GRAPH_ORCHESTRATOR ? `${BASE}/graph` : BASE;

/**
 * Standard (non-streaming) chat call.
 */
export async function sendCascadeMessage(request) {
  const res = await fetch(`${CHAT_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Cascade request failed');
  }
  return res.json();
}

/**
 * Streaming chat. Returns an async generator of parsed SSE events.
 * Yields:
 *   { type: 'meta',  intent, tool, followups }
 *   { type: 'chunk', text }
 *   { type: 'done' }
 */
export async function* streamCascadeMessage(request) {
  const res = await fetch(`${CHAT_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    throw new Error(`Stream error: ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6).trim();
      if (payload === '[DONE]') {
        yield { type: 'done' };
        return;
      }
      try {
        const parsed = JSON.parse(payload);
        if (parsed.intent !== undefined) {
          yield { type: 'meta', ...parsed };
        } else if (parsed.chunk !== undefined) {
          yield { type: 'chunk', text: parsed.chunk };
        } else if (parsed.error) {
          yield { type: 'error', error: parsed.error };
        }
      } catch {
        // ignore malformed lines
      }
    }
  }
}

/**
 * @deprecated Apply Recommendation no longer calls the backend.
 * It is handled entirely in the frontend via kpiStore.applyRecommendationLocal(),
 * exactly like a manual slider drag — frontend-only, never persisted to the DB.
 * This function is kept only so old imports don't crash; it is not called anywhere.
 */
export async function applyRecommendation(interventions) {
  console.warn(
    'applyRecommendation(): deprecated API call attempted. ' +
    'Use kpiStore.applyRecommendationLocal() instead — Apply is frontend-only now.'
  );
  return { ok: false, applied: [], not_found: interventions.map(i => i.name), message: 'Deprecated endpoint.' };
}

/**
 * Trigger RAG document ingestion.
 */
export async function triggerIngestion(rebuild = false) {
  const res = await fetch(`${BASE}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rebuild }),
  });
  if (!res.ok) throw new Error('Ingestion trigger failed');
  return res.json();
}

/**
 * Health check — returns LLM/RAG status.
 */
export async function getCascadeHealth() {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}
