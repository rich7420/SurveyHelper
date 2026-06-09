/**
 * surveyHelper ambient recognition (roadmap Theme A).
 *
 * On every turn, cheaply check whether the user is talking about a paper already in
 * the surveyHelper graph (via GET /recognize — local DB, no LLM), and if so inject
 * what we know into the prompt so the agent is *ambiently aware* with no tool call.
 * Shallow in-graph papers get a low-priority background `deepen` enqueued.
 */
import { definePluginEntry, type OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

const DEFAULT_ENDPOINT = "http://host.docker.internal:8765";
// Cheap pre-filter: only call /recognize when the text plausibly references a paper.
const PAPER_HINT = /arxiv|\b\d{4}\.\d{4,5}\b|et al\.?|\bdoi\b|\bpaper\b|\bpre[- ]?print\b/i;

function userText(event: unknown): string {
  const e = event as Record<string, unknown> | undefined;
  const raw =
    (e?.prompt as string) ??
    (e?.input as string) ??
    (e?.userInput as string) ??
    (e?.text as string) ??
    "";
  return typeof raw === "string" ? raw : String(raw ?? "");
}

export default definePluginEntry({
  id: "surveyhelper",
  name: "surveyHelper ambient recognition",
  register(api: OpenClawPluginApi) {
    const endpoint =
      ((api.config as Record<string, unknown> | undefined)?.endpoint as string) ||
      process.env.SURVEYHELPER_URL ||
      DEFAULT_ENDPOINT;

    api.on(
      "before_prompt_build",
      async (event: unknown) => {
        try {
          const text = userText(event).slice(0, 500);
          if (text.length < 4 || !PAPER_HINT.test(text)) return undefined;

          const res = await fetch(
            `${endpoint}/recognize?mention=${encodeURIComponent(text)}`,
            { signal: AbortSignal.timeout(1500) },
          );
          if (!res.ok) return undefined;
          const r = (await res.json()) as {
            in_graph?: boolean; paper_id?: number; title?: string; tldr?: string;
            user_state?: string; deep_analyzed?: boolean; references?: number;
            connections?: { title?: string }[];
            in_your_reading?: { title?: string; hops?: number; state?: string }[];
          };
          if (!r.in_graph) return undefined;

          // shallow + in-graph -> quietly deepen in the background (fire and forget)
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
