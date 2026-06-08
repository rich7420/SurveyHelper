# Heartbeat — surveyHelper notifications

On each heartbeat, check for finished surveyHelper background work and surface it.

1. Call the surveyHelper MCP tool **`pending_notifications()`**.
2. If `count` is 0 → there is nothing to report. Reply with `HEARTBEAT_OK` and stop.
3. If `count` > 0 → for each notification, write the user one short line based on `kind`:
   - `deep_ready` → "Deep analysis ready for <title>." (offer to show it)
   - `synthesis_ready` → "Graph synthesis ready for <root/topic>."
   - `proactive_digest` → relay the digest payload (e.g. "3 new papers on your <line>").
   - `budget_paused` → "A survey job paused on budget — confirm to continue?"
   - `job_failed` / `unimplemented` → mention briefly only if relevant.

Keep it to a short digest — never one message per paper (plan §17). Reading the
notifications marks them delivered, so don't repeat them next beat.
