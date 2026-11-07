# ORION: the explanation layer

ORION explains the mission. It **never controls it**: the deterministic engine owns truth, and
ORION only reads a frozen snapshot of facts derived from it.

```
Simulation truth ─► MissionContext (facts with ids) ─► provider ─► grounding validation ─► answer
                         ▲ science evidence                         │ fails?
                                                                    └► deterministic mock (flagged)
```

## Components (`app/ai/`)

| Piece | File | Role |
|---|---|---|
| `MissionContext`, `build_context` | `context.py` | Frozen, read-only facts: phase, status, outcome, 21 key metrics, active alerts, last 10 decisions, root-cause trace nodes/edges, matching evidence. Every fact has a stable id (`metric:power.battery_soc`, `alert:co2_high`, `decision:dec_…`, `trace:metric:…`, `evidence:bvad_o2_consumption`). |
| `AIProvider` | `provider.py` | `async complete(request) -> str` (JSON). |
| `MockAIProvider` | `mock.py` | Deterministic, offline, free. Builds answers only from facts and cites each. Default provider *and* the fallback. |
| `OpenAICompatibleProvider` | `provider.py` | Any `/chat/completions` endpoint (Ollama locally for free, OpenRouter, vLLM…). `temperature=0`, JSON mode. Errors are wrapped without leaking keys or response bodies. |
| `ORIONService` | `orion.py` | Prompting, validation, fallback, citations. |

ORION modules cannot import the engine's write paths, the database, repositories or services
(enforced by `tests/test_architecture.py`).

## Response contract

```json
{
  "topic": "why", "tick": 65,
  "segments": [{"text": "Causal chain: Decision set_subsystem_mode → Mode of CO2 removal → …",
                "citations": ["trace:decision:dec_…", "trace:metric:control.mode.co2_scrubber", "…"]}],
  "unavailable": [],
  "citations": [{"id": "…", "label": "…", "source": "trace", "url": null}],
  "provider": "mock", "grounded": true, "fallback_used": false, "validation_issues": []
}
```

Topics: `state_summary`, `why` (requires `metric`; uses a full root-cause trace with
counterfactuals), `decision_impact`, `free_question`. When information is missing the answer
says so in `unavailable` (e.g. "causal trace (no target metric was traced)") instead of
guessing.

## Grounding rules (enforced on every provider's output)

1. Output must parse as `{"segments": [{"text", "citations"}], "unavailable": []}` with size
   limits.
2. Every citation must be a fact id present in the context.
3. Every number in a segment must match (within rounding, or as a percentage of a fraction) a
   value or label number of a fact **cited in that segment**, or the current tick.

If any rule fails, or the provider errors or times out, ORION returns the mock's grounded
answer, sets `fallback_used: true` and lists `validation_issues`. A hallucinated "oxygen will
last 400 days" never reaches the player (tested).

## Prompt-safety boundaries

* The system prompt states the rules and declares the question block untrusted.
* The player question is sanitised (control characters stripped, 500-char cap) and placed in
  a `<question>` block **after** the `<context>` block.
* Even a fully compliant-looking injected answer must still pass grounding validation, and
  ORION has no tool or write access to act on instructions anyway.

## Configuration

```bash
ODYSSEY_AI_PROVIDER=mock                       # default, no key
# Free local model via Ollama:
ODYSSEY_AI_PROVIDER=openai_compatible
ODYSSEY_AI_BASE_URL=http://localhost:11434/v1
ODYSSEY_AI_MODEL=llama3.1
# Hosted (paid) endpoints additionally need ODYSSEY_AI_API_KEY.
```

A misconfigured provider (missing URL or model) logs a warning and uses the mock. Choosing a
production provider and ORION's personality are open product decisions
([D11](USER_DECISIONS_REQUIRED.md#d11-orion-provider-and-personality)). Adding Gemini natively
means implementing `AIProvider.complete`.
