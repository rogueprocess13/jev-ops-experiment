# Jev API notes

Consulted: 2026-09-29. Primary source: https://thejevai.com/docs. Cross-checked against the Pydantic AI TypeSafe page (https://pydantic.dev/docs/ai/models/typesafe/), which agrees on model names, `TYPESAFE_API_KEY`, and the choice/rubric/boolean question types.

Not used: other sites found by search (blog posts, community sites, unofficial GitHub notes). One of them (jevai.org) describes a different endpoint (`/v1/decisions`) and does not match the official docs, so it was ignored.

## Endpoint and auth

- `POST https://thejevai.com/v1/systemone`
- `Authorization: Bearer <API_KEY>`, `Content-Type: application/json`
- API keys: https://thejevai.com/settings/apikeys
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
- Pricing (https://thejevai.com/pricing, checked 2026-09-30): credit packs only (Starter $10 = 100,000 credits, Pro $100 = 1,000,000, Enterprise $1,000 = 11,000,000). No per-token or per-request rate is published, so the project has no default price.
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

Environment variables: `JEV_API_KEY` (required), `JEV_API_URL` (default `https://thejevai.com/v1/systemone`), `JEV_MODEL` (default `jev-latest`), `JEV_TIMEOUT_S` (default 30), `JEV_MAX_RETRIES` (default 3).

The model version that answered is in the response `model` field. It is recorded per run, because `jev-latest` may change over time.

## Python

Python 3.10 or newer. Runtime deps: `requests`, `python-dotenv`. Test dep: `pytest`.
