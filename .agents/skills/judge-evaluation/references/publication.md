# Publish the completed evaluation

Use the project helpers; Langfuse's own judge is not run. The human-approved name
and source selection are required before publication. One call to this skill
authorizes the local judgment and its Cloud publication, so do not ask again.

Create `publication.json` in the first selected judge run directory:

```json
{
  "name": "User-approved experiment name",
  "members": [
    {"source": "absolute source directory", "judge": "absolute llm-judge run directory"}
  ]
}
```

List every selected source exactly once with its finalized judge run. Keep the plan
when retrying upload. To compare a later change, create a new plan using that new
source and judge run. The helper derives a stable experiment identity from source
and judge identities, and adds a short suffix to the approved display name.
Dataset items are the exact original task plus domain/task/trial/seed. No expected
answer is generated. A changed case set forms a different dataset instead of silently
comparing unrelated inputs. One experiment cannot contain duplicate cases.

Run from the project root with credentials loaded:

```powershell
uv run --env-file .env python -m evals.publish_evaluation "<publication.json>"
```

If uv's launcher is broken, use the actual installed uv executable, or load .env
using python-dotenv before invoking the helper. Never print keys or put them in
command arguments. Do not silently change LANGFUSE_BASE_URL.

The helper reuses source traces, attaches judge observations and stable-ID scores,
and uses the official SDK experiment runner to publish saved judgment outputs.
The runner does not call a model or judge: each small experiment result trace
contains the saved judgment and a link to its existing source conversation.
It does not duplicate conversation observations or their token/cost records.
Do not use a standalone legacy dataset_run_items.create call: it can succeed
without creating the experiment attributes required by the v4 UI. Full actual
evidence is in score comments and evaluator output. Official scores are also linked
to the experiment item. For aggregate dashboards select the experiment item scope;
do not sum source-root scores and experiment-item scores together. Confirmed
experiment scores are not sent again. After an uncertain score write, inspect its
recorded score ID remotely before repairing its receipt; ID alone is insufficient
to prevent duplicates across dates.

Publication receipts live in `<source>/langfuse/<project-fingerprint>.json`.
Keep them with the source files. Concurrent publication is rejected by a lock.
After an uncertain observation upload the receipt stays pending: do not delete
receipts/locks or emit another trace just to get past an error. Confirm the saved
trace/observation remotely before repairing its receipt. Score retries reuse IDs.

For a trace uploaded before receipts existed, inspect it in the configured project
and adopt it rather than copying its conversation again:

```powershell
uv run --env-file .env python -m evals.langfuse_export "<source>" --trial 0 --adopt-trace "<verified trace ID>"
```

The helper checks source hash and simulation identity, checks recording completeness,
and reuses the existing official score ID. Never adopt based only on task/trial.

`publication.published.json` contains publication links after all registrations
succeed. Confirm the experiment and its cases through Langfuse's API/CLI before
claiming end-to-end UI verification. Do not claim that a successful mocked test
proves Cloud rendering. Return the approved name, published case count, unresolved
judge count, and the dataset/trace links. The user should not need to request an
additional upload or find evidence by message index.
