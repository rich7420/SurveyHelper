/**
 * surveyHelper ambient recognition (compiled). Source: ../index.ts
 * On every turn, inject what surveyHelper knows about a mentioned paper (GET /recognize,
 * local DB, no LLM), so the agent is ambiently aware with no tool call; deepen shallow ones.
 */
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const DEFAULT_ENDPOINT = "http://host.docker.internal:8765";
const PAPER_HINT = /arxiv|\b\d{4}\.\d{4,5}\b|et al\.?|\bdoi\b|\bpaper\b|\bpre[- ]?print\b/i;

function userText(event) {
  const raw =
    event?.prompt ?? event?.input ?? event?.userInput ?? event?.text ?? "";
  return typeof raw === "string" ? raw : String(raw ?? "");
}

export default definePluginEntry({
  id: "surveyhelper",
  name: "surveyHelper ambient recognition",
  register(api) {
    const endpoint =
      api.config?.endpoint || process.env.SURVEYHELPER_URL || DEFAULT_ENDPOINT;

    api.on(
      "before_prompt_build",
      async (event) => {
        try {
          const text = userText(event).slice(0, 500);
          if (text.length < 4 || !PAPER_HINT.test(text)) return undefined;

          const res = await fetch(
            `${endpoint}/recognize?mention=${encodeURIComponent(text)}`,
            { signal: AbortSignal.timeout(1500) },
          );
          if (!res.ok) return undefined;
          const r = await res.json();
          if (!r.in_graph) return undefined;

          if (!r.deep_analyzed && r.paper_id) {
            void fetch(`${endpoint}/deepen`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ paper_id: r.paper_id }),
              signal: AbortSignal.timeout(1500),
            }).catch(() => {});
          }

          const related = (r.connections ?? [])
            .slice(0, 2)
            .map((c) => c.title)
            .filter(Boolean)
            .join("; ");
          const reading = (r.in_your_reading ?? [])
            .slice(0, 2)
            .map((x) => `"${x.title}" (${x.hops}h, ${x.state})`)
            .join("; ");
          const lines = [
            `[surveyHelper memory] This paper is already in your research graph: "${r.title}".`,
            r.tldr ? `  Summary: ${r.tldr}` : "",
            r.user_state ? `  You previously marked it: ${r.user_state}.` : "",
            `  ${r.references ?? 0} references tracked` +
              (r.deep_analyzed ? ", deep-analyzed." : " (deepening in the background)."),
            related ? `  Related in your graph: ${related}.` : "",
            reading ? `  Connected to what you've read: ${reading}.` : "",
          ]
            .filter(Boolean)
            .join("\n");

          return { prependContext: lines };
        } catch {
          return undefined;
        }
      },
      { timeoutMs: 2000 },
    );
  },
});
