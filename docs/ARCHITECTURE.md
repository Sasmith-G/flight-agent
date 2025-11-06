# Architecture

## Goal

Turn a flight disruption into a proactive, grounded, actionable passenger notification
with zero human intervention — while keeping the LLM on a short leash.

## The pipeline

The agent is a compiled **LangGraph** state machine. State (`AgentState`) is a typed
dict threaded through six nodes:

| Node | External system | Output added to state |
|---|---|---|
| `check_status` | Amadeus On-Demand Flight Status (`/v2/schedule/flights`) | `FlightStatus` (scheduled vs estimated timings, cancellation flag) |
| `assess_disruption` | Amadeus Flight Delay Prediction (`/v1/travel/predictions/flight-delay`) | `DisruptionEvent` (type, delay minutes, P(delay>2h)) |
| `search_alternatives` | Amadeus Flight Offers Search (`/v2/shopping/flight-offers`) | `list[RebookingOption]` sorted by earliest arrival |
| `retrieve_policies` | Local RAG corpus (BM25) | `list[PolicyPassage]` with source + score |
| `draft_recommendation` | Anthropic API (Claude) | `Recommendation` (message + grounding) |
| `notify` | Twilio or console | delivery reference |

Routing: after `assess_disruption`, a conditional edge ends the run unless
`DisruptionEvent.actionable` — cancellation, or delay ≥ 120 minutes (the EU261
right-to-care threshold). On-time flights never generate a notification.

Every node appends to a `trace` list, so each run is fully auditable.

## Safety model for the LLM

The central design constraint: **the LLM formats; it does not decide.**

- Facts (flight, delay, options, prices, seats) come from the Amadeus APIs.
- Entitlements (compensation, care, rebooking rights) come from retrieved policy
  passages; the system prompt forbids claims without a provided passage and requires
  naming the source.
- Compensation is always phrased as "likely eligible" because eligibility depends on
  the disruption cause (extraordinary circumstances exemption) — this rule lives in
  the duty-of-care matrix document, so it is retrievable and versionable, not
  hard-coded in the prompt.
- `MockLLM` renders the same message deterministically, which lets end-to-end tests
  assert on message content in CI without an API key.

## Mock/live parity

`AmadeusClient` is an ABC with two implementations:

- `LiveAmadeusClient`: OAuth2 client-credentials with token caching, httpx, response
  normalisation into pydantic models, graceful degradation when the (beta) delay
  prediction endpoint errors.
- `MockAmadeusClient`: three recorded scenarios (`on_time`, `delay` = AF1234 NCE→CDG
  +3h10, `cancellation`) whose values mirror real test-environment response shapes.

The graph receives the client by injection, so mock vs live is a configuration
change (`AGENT_MODE`), not a code path change. The same applies to `LLM`
(Anthropic/Mock) and `Notifier` (Twilio/console).

## Retrieval choices

The corpus is four markdown policy documents chunked at `##` section level and
indexed with BM25 (`rank-bm25`). For this corpus — small, keyword-dense, legally
precise — lexical retrieval outperforms embeddings on auditability and determinism,
and adds zero model downloads. The `PolicyRetriever` class is intentionally the
single seam for swapping in a vector store (ChromaDB + embeddings) when the corpus
grows to many carriers and languages.

## What production would add

- A monitoring daemon (scheduler/queue) instead of a one-shot CLI run.
- Flight Create Orders integration for actually executing the chosen rebooking.
- Observability: traces exported to an LLM-observability tool (e.g. Langfuse),
  delivery metrics, cost per notification.
- An evaluation harness scoring groundedness of live LLM outputs against the
  retrieved passages, run in CI.
- PII handling review (passenger contact data) and rate limiting.
