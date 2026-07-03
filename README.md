# ant-farm

A surveying instrument for contested questions. It runs N parallel reasoning traces
across diversified sensors, harvests their findings into an accumulating claim corpus,
and issues a **coverage certificate** — a quantified statement of how much of the argument
space has been mapped, with the holes named.

It has no opinion. Its product is a **map**: the stable positions (basins), the
disagreements that decide between them (cruxes), the unresolved conflicts (ridges), and
the unexplored regions (holes). Opinionated consumers (the dialectic-plugin sublation
loop, distill, forge) occupy positions on the map and argue for them.

> **ant-farm surveys; dialectic advocates.** A reasoning session is disposable; a survey
> corpus is an asset that improves with every run.

## Status

Design phase. The full design lives in
[`docs/specs/2026-07-03-ant-farm-design.md`](docs/specs/2026-07-03-ant-farm-design.md).
No implementation yet.

## The novel contribution

Four published literatures supply the parts; nobody has assembled them:

1. Unseen-mass estimation (Good-Turing/Chao) applied to LLM-generated **arguments on
   subjective questions** — existing work targets factual hallucination only.
2. Top-down morphological fields (Zwicky) fused with bottom-up sampled coverage.
3. **Correlation-discounted effective sample size** feeding the coverage estimator — no
   prior art anywhere.
4. A NOVA-aware verification floor gating late-stage discoveries against contamination.

Positioning vocabulary: *quantified theoretical saturation*.

## Component vocabulary

Survey/cartography metaphor throughout.

| Term | Meaning |
|---|---|
| **atom** | One self-contained claim/consideration/evidence record. The unit of storage, embedding, counting. |
| **vantage** | Sensor geometry for a trace: model family, persona, frame, starting hypothesis, round. |
| **farm** | One reasoning trace: a hypothesis explored through expand → refute → sublate rounds. |
| **well** | The full corpus: every atom ever recorded, superseded and conceded included. Nothing deleted. |
| **view** | The computed HEAD: current best-confidence state, small and clean, the default retrieval target. |
| **map** | The rendered topology: basins, cruxes, ridges, holes. |
| **certificate** | The coverage report: scalar + curve + named-gap grid, correlation-discounted. |
| **sentinel** | A run-opening pass that checks standing tripwires against the world and propagates any that fired. |

Agents: **surveyor** (framing), **scout** (runs a farm), **blind-critic** (refutation),
**hole-finder** (gap probing), **stitcher** (ACH + map), **sentinel**, **curator**
(renders the view).

## Where this came from

Extracted from the dialectic-plugin v2 redesign (2026-07-03). Grew out of three research
streams — SOTA multi-pass/adversarial LLM reasoning, richer philosophical primitives, and
coverage-quantification prior art — plus the design conversation that turned parallel
reasoning traces into a coverage-certified survey instrument.

## Next steps (open)

See §13 of the spec. Sequencing suggestion: corpus schema + reducer first (everything
depends on it), then the survey pipeline, then the certificate, then the dialectic-plugin
consumer seam. Implementation plan not yet written — start there in the next session
(`writing-plans` skill).
