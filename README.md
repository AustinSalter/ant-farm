# ant-farm

A surveying instrument for contested questions. N parallel reasoning farms explore
rival hypotheses under adversarial critique; their findings accumulate into a corpus
that compounds across runs; the instrument reports how much of the argument space has
been mapped — with the holes named.

> **ant-farm surveys; dialectic advocates.** A reasoning session is disposable; a
> survey corpus is an asset that improves with every run.

ant-farm has no opinion. Its product is a **map** — stable positions (basins), the
disagreements that decide between them (cruxes), unresolved conflicts (ridges),
unexplored regions (holes) — and a **coverage certificate**: a quantified statement of
how much terrain the survey actually covered.

## How it works

```
 ┌──────────┐ fired tripwires ┌──────────┐ rival hypotheses, null included
 │ SENTINEL │────────────────▶│ SURVEYOR │ (stasis, base rates, Zwicky field)
 └──────────┘                 └────┬─────┘
                                   │ one farm per rival
                 ┌─────────────────▼──────────────────┐
                 │  FARM × N  (parallel, evidence-    │
                 │  blind to peers until stitch)      │
                 │                                    │   ┌──────────────┐
                 │  round: sublate → expand →         │◀──│ BLIND-CRITIC │
                 │  compress → decide                 │──▶│  (authorless │
                 │                                    │   │    trace)    │
                 │  emits atoms + edges with warrants │   └──────────────┘
                 └─────────────────┬──────────────────┘
                                   │ harvest: events → reducer → corpus
       ┌──────────┐          ┌─────▼───────┐          ┌─────────┐
       │ STITCHER │─────────▶│ HOLE-FINDER │─────────▶│ CURATOR │
       │ACH matrix│          │ gap probes  │          │ renders │
       └──────────┘          └─────────────┘          └─────────┘
```

Each farm round runs the dialectic protocol: sublation with a preservation gate,
expansion with meta-probes, compression to a falsifiable state, and a decision —
CONTINUE | CONCLUDE | ELEVATE | CONCEDE — gated by evidence. The pass content is
ported from dialectic-plugin v1, where it was proven; the loop is decomposed across
fresh contexts with continuity in the farm directory; critique is externalized to a
critic that reads the trace as an authorless third-party document.

Deterministic where it must be: orchestration is a Claude Code dynamic workflow,
every gate a model could rationalize past is enforced in Python (`python -m antfarm`),
and the JSONL event log is the source of truth — corpus state is a pure fold, always
recomputable from events.

## The corpus

| Term | Meaning |
|---|---|
| **atom** | One self-contained claim, evidence record, or consideration — the unit of storage, embedding, and counting. |
| **vantage** | Sensor geometry for an observation: model family, persona, farm, round. |
| **farm** | One reasoning trace: a hypothesis explored through sublate → expand → compress rounds. |
| **well** | The full corpus: every atom ever recorded, superseded and conceded included. Nothing deleted. |
| **view** | The computed HEAD: live, verified, diagnostic atoms — the default retrieval target. |
| **map** | The rendered topology: basins, cruxes, ridges, holes. |
| **certificate** | The coverage report: scalar + curve + named-gap grid, correlation-discounted. |

Storage discipline, enforced by validators and gates rather than convention:

- Append-only. Runs never edit history; supersession marks, never deletes.
- Re-found ≠ duplicate: an entailment-matched atom gains a sighting and a vantage.
- View admission is computed. No agent — curator included — can admit an atom.
- Every `supports` edge carries a warrant: the rule licensing the inference, stated
  so it can be attacked.

## Status

Corpus core (plan 1) is merged: the `antfarm` Python package — content-hash atom
schemas, append-only event log, deterministic reducer with entailment merge, graph
queries, view gate, chroma stores, keel transcript export, counterfactuals, Obsidian
render — with the full gate (tests, lint, types, real-embedding eval, end-to-end
smoke) green in CI. The survey pipeline (plan 2) is implemented: the `python -m antfarm`
CLI, the seven survey agents, and the `workflows/survey.js` orchestrator. Run a survey
via the `/survey` skill (requires Claude Code >= 2.1.154 with dynamic workflows). The
coverage certificate (plan 3) and the dialectic-plugin v2 consumer seam (plan 4) are
next. The full design lives in
[`docs/specs/2026-07-03-ant-farm-design.md`](docs/specs/2026-07-03-ant-farm-design.md).

## The novel contribution

Four published literatures supply the parts; nobody has assembled them:

1. Unseen-mass estimation (Good-Turing/Chao) applied to LLM-generated **arguments on
   subjective questions** — existing work targets factual hallucination only.
2. Top-down morphological fields (Zwicky) fused with bottom-up sampled coverage.
3. **Correlation-discounted effective sample size** feeding the coverage estimator.
4. A verification floor gating late-stage discoveries against contamination.

Positioning vocabulary: *quantified theoretical saturation*.

## Consumers

**[dialectic-plugin](https://github.com/AustinSalter/dialectic-plugin) v2 (the
advocate).** The seam is two-way — *seed, consume, compound*. A dialectic session
opens from a corpus warm-start brief, distill and forge read the view (refutatio from
the strongest surviving rival; decision points from died-because records), and the
session's atoms harvest back into the corpus at session end. Advocacy enriches the
map instead of evaporating.

**[keel](https://github.com/AustinSalter/keel) (the geometer).** Reads the trace
exhaust: retained farm transcripts in keel's schema, plus counterfactuals (shuffle,
graft, persona-swap) that give ground truth by construction. The seam is deliberately
thin — ant-farm optimizes for coverage, never for keel's metric, so keel's stimuli
stay independent of its measure.

## Where this came from

Extracted from the dialectic-plugin v2 redesign (2026-07-03): three research streams —
multi-pass adversarial LLM reasoning, richer philosophical primitives, and
coverage-quantification prior art — converged on turning parallel reasoning traces
into a coverage-certified survey instrument.
