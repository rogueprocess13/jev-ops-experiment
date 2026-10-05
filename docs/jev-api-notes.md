# Jev API notes

Consulted: 2026-09-29, corrected 2026-10-05. Primary source: TypeSafe's API reference, https://docs.typesafe.ai/api. Jev is TypeSafe's model. Cross-checked against the Pydantic AI TypeSafe page (https://pydantic.dev/docs/ai/models/typesafe/), which agrees on model names, `TYPESAFE_API_KEY`, and the choice/rubric/boolean question types.

Correction (2026-10-05): the first version of these notes used https://thejevai.com/docs as the primary source. That site is not TypeSafe. Its footer says "Jev AI is an independently operated product and is not affiliated with, operated by, or endorsed by TypeSafe." A key from the TypeSafe console (`apikey_` prefix) gets `401 {"code":-1,"message":"Invalid API key."}` on `https://thejevai.com/v1/systemone` and works on `https://api.typesafe.ai/v1/systemone` (a fake key gets 401 there; the real key gets 200 with answers, model `jev-1.13.0`). The request and response shapes below matched in real runs on 2026-10-05. Details first taken from thejevai.com and not yet re-checked against docs.typesafe.ai are marked.

Not used: other sites found by search (blog posts, community sites, unofficial GitHub notes). One of them (jevai.org) describes a different endpoint (`/v1/decisions`) and was ignored.

## Endpoint and auth

- `POST https://api.typesafe.ai/v1/systemone`
- `Authorization: Bearer <API_KEY>`, `Content-Type: application/json`
- API keys: https://console.typesafe.ai/
- No official Python SDK was found in the docs. This project calls the HTTP API directly with `requests`. (Pydantic AI has a `TypeSafeModel`, but it adds a large dependency for no gain.)

## Request

Required top-level fields: `state` (string, object or array), `model` (`"jev-latest"`), `questions` (map of your own IDs to question objects).

Question types:

- `choice`: `{"type": "choice", "instructions": "...", "criteria": {"option": "description", ...}}`. Up to 255 options.
- `score`: `{"type": "score", "instructions": "...", "criteria": ["level0", "level1", ...]}`. 2 to 10 levels.
- `noul` (yes/no): `{"type": "noul", "instructions": "...", "criteria": {"true": "...", "false": "..."}}`. `criteria` is optional.

## Response

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "<question id>": { "type": "choice", "choice": "billing",
                        "probabilities": {"billing": 0.88, "technical": 0.12},
                        "confidence": 0.81 }
  },
  "usage": {"input_tokens": 307, "output_tokens": 20}
}
```

- `noul` answers: `{"type": "noul", "noul": 0.95}`. The number is the probability of "yes". There is **no separate confidence field** for noul.
- `score` answers: `score`, `legend`, `probabilities`, `confidence`.

## Usage, timing and cost

- `usage.input_tokens`, `usage.output_tokens`: token counts.
- `elapsedMs`: "time from sending the request to receiving the result, including validation". Not pure inference time. The docs do not say exactly where it sits, so the adapter reads it at the top level and falls back to `usage.elapsedMs`.
- The docs say usage "may include cost in USD" but do not name the field. The adapter takes any numeric `usage` key containing "cost" as reported cost, and keeps the raw `usage` object.
- Pricing: TypeSafe's API reference (checked 2026-10-05) gives no per-token or per-request price, and real responses carry no cost field, so the project has no default price. (The credit packs at https://thejevai.com/pricing belong to that separate, unaffiliated site, not to TypeSafe.)
- `elapsedMs` and the "may include cost" wording above come from thejevai.com and are not yet re-checked against docs.typesafe.ai. Real responses on 2026-10-05 had neither.
- No request ID or rate-limit headers are documented.

## Errors

401 invalid key, 422 validation error, 429 rate limit, 529 overloaded. Retry 429 and 529 with exponential backoff.

## Context limits

Pydantic AI page: 32k tokens per request. Not a concern for one small observation per request.

## Mapping for this project

One request per run, four questions:

| Decision | Jev question type | Reading the answer |
|---|---|---|
| `severity` | `choice`: normal, degraded, high, critical | `choice`, `probabilities`, `confidence` |
| `action` | `choice`: observe, investigate, restart, escalate | `choice`, `probabilities`, `confidence` |
| `probable_cause` | `choice`: none, resource_exhaustion, dependency_failure, application_bug, configuration, network, unknown | `choice`, `probabilities`, `confidence`. Scored separately, not part of PASS/FAIL. |
| `human_review` | `noul` | `noul` is P(yes). Decide `yes` if >= 0.5, else `no`. Record the raw probability. |

Overall confidence for a run: the mean of the `severity` and `action` choice confidences (not `probable_cause`). Per-field confidence, the raw noul probability, and full probability tables are stored too. Noul has no confidence value, so it is not folded into the overall figure. The 0.5 threshold is our choice, not part of the API.

## Configuration

Environment variables: `JEV_API_KEY` (required), `JEV_API_URL` (default `https://api.typesafe.ai/v1/systemone`), `JEV_MODEL` (default `jev-latest`), `JEV_TIMEOUT_S` (default 30), `JEV_MAX_RETRIES` (default 3).

The model version that answered is in the response `model` field. It is recorded per run, because `jev-latest` may change over time.

## Python

Python 3.10 or newer. Runtime deps: `requests`, `python-dotenv`. Test dep: `pytest`.

## Tier 2 use (OpenTelemetry Demo)

Tier 2 reuses the same endpoint and question types through `JevClient.send` (transport only) and `tier2/jev_adapter.py` (questions and parsing). No new API features are used.

| Question | Type | Notes |
|---|---|---|
| `incident_detected` | `noul` | P(yes). Incident if >= 0.5 (our threshold). No confidence value, as for any noul. |
| `affected_service` | `choice` | 19 options (18 demo services plus `none`), well under the 255 limit. Same list every run. |
| `diagnosis` | `choice` | 7 options. |
| `recommended_action` | `choice` | 6 options. |

- State key is `observations` (Tier 1 uses `server_observations`). The API takes an arbitrary `state` object.
- Overall confidence is the mean of the three choice confidences when present, else `null`. The noul probability is stored separately in the raw response.
- Jev's reply has no free-text reasoning field in the docs checked, so `reasoning` is `null` unless a `reasoning` string appears in the body. The raw response is always stored.
- **Size.** The 32k-token limit above comes from the Pydantic AI page, not from the Jev API docs, so it is unverified for this endpoint. A real observation can be large, so the builder caps it at 60,000 bytes (about 15k tokens at roughly 4 bytes per token) before the questions are added. If real runs show Jev rejecting requests, lower `BYTE_BUDGET` in `tier2/observation.py` and record the finding.
