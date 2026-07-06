# ant-farm: Design Spec

**Date:** 2026-07-03
**Status:** Draft for review
**Repos:** `ant-farm` (new — the instrument), `dialectic-plugin` (v2 — the first consumer), `keel` (second consumer — trace exhaust)

---

## 1. What it is

ant-farm is a surveying instrument for contested questions. It runs N parallel reasoning
traces ("farms") across diversified sensors, harvests their findings into an accumulating
claim corpus, and issues a **coverage certificate**: a quantified statement of how much of
the argument space has been mapped, with the holes named.

It has no opinion. Its product is a **map**: the stable positions (basins), the
disagreements that decide between them (cruxes), the unresolved conflicts (ridges), and
the unexplored regions (holes). Consumers with opinions — dialectic-plugin's sublation
loop, distill, forge — occupy positions on the map and argue for them.

The division of labor: **ant-farm surveys; dialectic advocates.** A dialectic session is
disposable; a survey corpus is an asset that improves with every run.

### The novel contribution

Four published literatures supply the parts; nobody has assembled them:

1. Unseen-mass estimation (Good-Turing/Chao) applied to LLM-generated **arguments on
   subjective questions** — existing work targets factual hallucination only.
2. Top-down morphological fields (Zwicky) fused with bottom-up sampled coverage.
3. **Correlation-discounted effective sample size** feeding the coverage estimator —
   no prior art anywhere.
4. A NOVA-aware verification floor gating late-stage discoveries against contamination.

Positioning vocabulary: *quantified theoretical saturation* — the term qualitative
research already accepts for "we have heard all the themes."

---

## 2. Core concepts

| Term | Meaning |
|---|---|
| **Atom** | One self-contained claim/consideration/evidence record. The unit of storage, embedding, and counting. |
| **Vantage** | Sensor geometry for a trace: model family, persona, frame, starting hypothesis, round. Recorded so coverage claims can cite *where we looked*, not just what we found. |
| **Farm** | One reasoning trace: a hypothesis explored through expand → refute → sublate rounds. |
| **Transcript** | The ordered raw record of one farm's reasoning as it flowed, retained per farm — the behavioral complement to the atom layer. |
| **Well** | The full corpus: every atom ever recorded, superseded and conceded included, fully traversable. Nothing is deleted. |
| **View** | The computed HEAD: current best-confidence state, small and clean, the default retrieval target. |
| **Map** | The rendered topology: basins, cruxes, ridges, holes. |
| **Certificate** | The coverage report: scalar + curve + named-gap grid, correlation-discounted. |
| **Sentinel** | A run-opening pass that checks standing tripwires against the world and propagates any that fired. |

---

## 3. Architecture

**Substrate: Claude Code dynamic workflows, exclusively.** The orchestration is a
JavaScript workflow script (`workflows/survey.js`); rounds, gates, budgets, and pruning
are deterministic code inspecting schema-forced agent outputs. There is no second
execution path: no stop-hook loop, no headless-process fan-out. (dialectic-plugin v1's
stop-hook state machine was a hand-rolled workflow runtime; v2 deletes it — both
implementations.)

Requirements this imposes: Claude Code ≥ 2.1.154, workflows enabled, paid plan. The
README states this plainly. Users without workflows can use dialectic-plugin v1.

### Agent roles (shipped as agent definitions)

| Agent | Context | Reads | Job |
|---|---|---|---|
| **surveyor** | fresh | question + prior corpus view | Framing: stasis, altitude, DISSOLVE check, reference class + base rate, Zwicky field, rival hypotheses (incl. null) |
| **scout** | fresh per round, continuity via its farm dir | own farm dir + view (warm start) | One round: sublate last round's critiques → expand → compress → emit atoms |
| **blind-critic** | fresh, blinded | one farm's serialized trace, **as an authorless external artifact** + the well | Refutation: warrant probe, severity grading, premortem, defeater classification |
| **hole-finder** | fresh | the view + certificate | Produce a consideration absent from the corpus, or fail trying |
| **stitcher** | fresh | all farms' compressed outputs + evidence inventory | ACH matrix, disagreement investigation, crux extraction, basin/frontier declaration |
| **sentinel** | fresh | standing tripwires | Check tripwires (web), flag fired ones, propagate blast radius |
| **curator** | fresh | reduced graph state | Render the view's prose and the Obsidian/map exports (rendering only — admission is computed) |

Evidence-backed blinding rules (non-negotiable, they carry the measured effect sizes):

- Critics never learn authorship; traces are presented as third-party documents
  (role-relabeling: +23–93pp error-admission; fresh context: d≈0.5–0.7).
- Producers never self-evaluate in their own context (self-correction blind spot: 64.5%,
  rising with reasoning complexity).
- Farms are evidence-blind to each other until stitch (independence is the product).
- No pass iterates to consensus; dissent is preserved, not resolved (deliberative-illusion
  failure mode: stance homogenization, factual attrition).

### Sensor diversity (evidence-ranked, spend in this order)

1. **Model families.** Same-model error correlation ≈ 0.4 and is not lowered by
   temperature or prompt perturbation; cross-family ≈ 0.08. Three farms across three
   families beat nine same-model farms. Family per farm is a vantage field.
2. **Mundane, varied personas + CoT.** Ordinary personas ("a procurement manager")
   restore knowledge partitioning; exotic ones change style, not content.
3. **Human atoms.** User-seeded considerations enter with `vantage.sensor: human` — the one
   sensor guaranteed outside the model class's blind spots. Runs must engage them.

---

## 4. Data layer

### 4.1 Source of truth: append-only run log

Each run appends JSONL event files (one per farm-round plus one per pipeline phase).
Runs never edit history. All agent output is schema-forced at the `agent()` call —
malformed records cannot enter the corpus.

**Node record**

```jsonc
{
  "id": "c-8f3a…",              // content hash — stable across runs
  "type": "claim",               // claim | evidence | tension | crux | hypothesis | source | vantage | tripwire
  "text": "…",                   // SELF-CONTAINED: no pronouns, no unresolved references; embeddable without context (validator-enforced)
  "vantage": {"run": "r7", "farm": "B", "family": "…", "persona": "…", "round": 2, "sensor": "model|human"},
  "status": "live",              // live | contested | superseded | conceded
  "superseded_by": null,
  "strength": 4,                 // evidence only, 1-5
  "diagnosticity": "high",       // high | med | none — vs. best rival, not in isolation
  "verified": true,              // passed the verification floor
  "sightings": 3,                // times independently re-found (feeds coverage math)
  "question_id": "q-…",
  "ts": "2026-07-03T…"
}
```

**Edge record**

```jsonc
{
  "src": "e-1c9d…", "dst": "c-8f3a…",
  "rel": "supports",             // supports | rebuts | undercuts | qualifies | bridges | depends_on | supersedes | scored_against
  "warrant": "…",                // Toulmin: the rule licensing this inference lives ON the edge — attackable
  "consistency": null,           // scored_against only: consistent | inconsistent | neutral
  "vantage": {…}, "ts": "…"
}
```

The atom **is** the chunk: chunking is a generation-time decision, never post-hoc
splitting. The marker vocabulary of dialectic v1 maps directly (`[BRIDGE: A→B]` → edge,
`[EVIDENCE]` → node type, Pollock's rebut/undercut → `rel` subtypes); v1 serialized a
graph into prose and regex-scraped it back — v2 stops pretending.

### 4.2 Corpus state: the wiki

A deterministic reducer folds run events into current state:

- **Merge operator = entailment clustering.** A re-found consideration is an
  *observation*, not a duplicate: increment `sightings`, attach the vantage, possibly
  upgrade status. Novel atoms create pages.
- **Supersession without deletion.** `status: superseded` + `supersedes` edge. Every
  claim page carries its full revision history — the argument's life story.
- **Conceded hypotheses stay on the map**, marked with their died-because record.

### 4.3 The view and the well

- **Well**: everything, labeled. Attackers (critics, hole-finders, sentinels) retrieve
  here — they want the contested and buried material.
- **View**: computed HEAD. Admission is a **computed gate** (status = live, verification
  passed, centrality/diagnosticity thresholds), rebuilt after every run; the curator
  renders prose but cannot admit atoms. Producers and consumers retrieve here by default.
- Every view node is one edge away from its standing challenges — *best-confidence thesis,
  challenges traversable*.
- **The view does not force convergence.** Where one basin dominates, the view is a
  thesis. Where the question is Pareto-shaped, the view is the **crux-conditional
  frontier**: "under weighting W1, basin A; under W2, basin B; the crux is X." Smallest
  honest summary, never a mean of incompatible positions.

**Rationale (RAG discipline):** retrieval over a raw accumulating corpus returns N
versions of each claim plus refuted cousins; noise defeats agent convergence before
reasoning quality matters. Tier filtering is the fix: two Chroma collections (`view`,
`well`), one routing rule (producers → view, attackers → well).

### 4.4 Stores

| Store | Content | Role |
|---|---|---|
| JSONL run logs | events | source of truth |
| Chroma `view` / `well` | embedded atom text + metadata filters (vantage, type, status, round) | coverage math ("same species" = embedding cluster), gap detection (low-density regions), dedup, retrieval |
| Graph state (start: JSONL + NetworkX in scripts; Kùzu when queries earn it) | nodes + edges | centrality (cruxes), community detection (basins), un-sublated-undercutter queries, blast-radius propagation |
| Obsidian render | one markdown page per view node, `[[wikilinks]]` for edges | free human map UI |
| Farm transcripts | ordered raw turns per farm (JSONL), vantage manifest header | blind-critic input; keel export substrate (§9.2) |

### 4.5 Farm transcripts (retained raw)

Each farm's transcript — the round-by-round reasoning as it flowed, one turn per
record — is a **first-class retained artifact**, not a disposable render. Atoms are the
analytical layer; the transcript is the behavioral record, and it is the only place the
farm's long-context reasoning survives (a graph of claims has no sequence, hence no
geometry). Two consumers already require it: the blind-critic reads it as an authorless
external document (§3), and keel measures activation geometry over it (§9.2).

Format: vantage as the manifest header; turns carry a total order. Field mapping targets
keel's existing `traces/` schema directly — `{turn, role, phase, iteration, content}`
with round → `iteration` and move type (sublate | expand | compress | critique) →
`phase` — so keel consumes farm transcripts with zero adaptation.

Retention note: dialectic v1 transcripts are keel's only current substrate, and v2
deletes v1. Without this artifact, shipping ant-farm would extinguish keel's data
source; with it, every survey run is also a corpus contribution.

---

## 5. The survey pipeline

One workflow run = seven phases. Phases 0–1 also run standalone (`--sentinel-only`,
`--frame-only`).

**Phase 0 — Sentinel** (skipped on first run). Check standing tripwires against the
world. Fired tripwire → mark claim contested → propagate along `depends_on` (centrality
= blast radius) → affected basins flagged in this run's brief.

**Phase 1 — Framing** (surveyor). Stasis level; altitude; **DISSOLVE** check (false
presupposition / fake binary → emit replacement question and stop); reference class +
base rate ("how often do theses shaped like this pay off?"); Zwicky field (dimensions ×
values, incoherent cells pruned) — the deductive possibility space; rival hypotheses
(2–4 incl. the null), warm-started from prior basins when the corpus has them.

**Phase 2 — Fan-out** (scout × N, parallel via `pipeline()`). Per farm, per round:
1. *Sublate* last round's critique reports (in-farm context: preservation gate,
   amputation check, Lakatos degeneration ledger — 2 consecutive novel-content-free
   patches force ELEVATE or CONCEDE).
2. *Expand* (abduction on anomalies; guided search; atoms emitted with warrants).
3. *Compress* (structured state; confidence as ordinal R/E/C bands).
Farm decisions: CONTINUE | CONCLUDE | ELEVATE | **CONCEDE** (with died-because).
CONCLUDE gates (script-enforced): ≥1 HIGH-severity falsification trigger ("would a false
thesis survive this?"), no un-sublated undercutters, degeneration ledger clean.

**Phase 3 — Refutation** (blind-critic per farm per round, interleaved with Phase 2 via
pipeline). Warrant probe (attack the licence, not the grounds), premortem ("it failed
12 months on — write the history"; output must become a named risk or be rebutted),
severity grading, rebutting/undercutting classification. Reports land in the farm's
critique dir as external artifacts.

**Phase 4 — Harvest & merge.** Entailment-cluster all new atoms against the corpus;
apply merge operator; run the **verification floor** — late-round "novel" atoms need
independent verification before `verified: true` (NOVA contamination trap: as genuine
discovery mass shrinks, unverified novelty is increasingly confabulation).

**Phase 5 — Stitch** (stitcher). ACH matrix (evidence × hypotheses; evidence consistent
with everything is non-diagnostic and discarded from support counts); winner-by-least-
inconsistency, never by confirmation count; investigate *only* disagreements between
farms; extract cruxes (high-centrality contested nodes); declare basin structure or
crux-conditional frontier; DISSOLVE remains available here too.

**Phase 6 — Certificate + gap-directed spawn decision.** Compute the certificate
(§6). If budget remains and holes are material, spawn additional farms **briefed at the
largest holes** (empty Zwicky cells, low-density embedding regions, hole-finder hits) —
active learning over argument space. Else finalize.

**Phase 7 — Materialize.** Reducer rebuilds view; curator renders map + Obsidian export;
farm transcripts written with vantage manifests and outcome metadata (the keel export,
§9.2); tripwires from falsification triggers and `revisit_when` conditions are
registered as standing sentinel queries.

---

## 6. The coverage certificate

Three metrics, always reported together — no single number is defensible alone:

1. **Scalar — coverage-corrected effective distinct considerations.**
   Entailment-cluster the corpus; coverage `C = 1 − f₁/n_eff` (Good-Turing; f₁ =
   singleton clusters); alphabet-size estimate for total discoverable considerations;
   Vendi score as the observed-diversity companion.
2. **Curve — rarefaction/extrapolation (iNEXT-style) with Chao1 lower bound.**
   "Runs so far found K; run N added ΔK; estimated unseen ≈ M; +N traces buys ≈ ΔK'."
   Resumes across runs — saturation is observable over the corpus lifetime.
   Extrapolation capped at 2–3× current sample (beyond is unreliable).
3. **Named-gap grid — recall against the Zwicky field + KPA-style coverage-at-threshold.**
   Which cells are stamped, which are provably empty. The only metric that names holes;
   blind by construction to unanticipated dimensions (say so on the certificate).

**Corrections (both mandatory):**

- **Correlation discount.** Compute inter-trace correlation (cluster co-membership
  across same-family vantages); derive **n_eff < n** (effective independent scans); feed
  n_eff, not n, into all estimates. Same-model ensembles are optimistically biased *by
  construction* — shared blind spots produce no singletons, so the estimator fails
  silently exactly where it matters. The certificate reports n, n_eff, and the family mix.
- **Scope statement.** All coverage is of the **sensor-reachable argument space**. The
  certificate lists the vantages run (scan geometry), not just returns — a dense cloud
  scanned from one vantage is one perspective at high resolution, not coverage.

**Adversarial line-item:** hole-finder survival streak (K consecutive failures to
produce an absent consideration), with early hit-rate reported as the test's severity —
a hole-finder that never succeeded is a weak test and its failures are worth less.

---

## 7. Primitives → mechanisms (carried into both repos)

| Primitive | Mechanism | Where |
|---|---|---|
| Chamberlin/Heuer ACH | rival fan-out; evidence × hypothesis matrix; win by least-inconsistency; non-diagnostic evidence discarded | Phases 1, 5 |
| Toulmin warrants | `warrant` on every supports-edge; warrant probe | schema, Phase 3 |
| Lakatos degeneration | revision ledger {trigger, change, novel_content}; 2 content-free patches → ELEVATE/CONCEDE | Phase 2 sublation |
| Popper/Mayo severity | falsification triggers graded ("would a false thesis survive?"); CONCLUDE needs ≥1 HIGH; hole-finder severity | Phases 2, 6 |
| Tetlock outside view | reference class + base rate at framing; prior → posterior stated | Phase 1 |
| Premortem | required probe; output becomes named risk or is rebutted | Phase 3 |
| Wittgenstein DISSOLVE | terminal decision at framing and stitch; replacement question required | Phases 1, 5 |
| Quine centrality | computed from depends_on graph; crux extraction; tripwire blast radius | Phases 0, 5 |
| Hegel Aufhebung | in-farm sublation (production act, needs continuity); supersession-without-deletion in storage | Phase 2, §4.2 |
| Mercier & Sperber | role-purity: producers never self-evaluate; design rationale, one sentence | §3 |

Cut as decoration (checks survive, citations go): Kolmogorov, category theory,
Miller's 7±2. Deferred to later: Walton scheme-tagging (~10 schemes with mandatory
critical questions).

**Confidence, unified:** R = defensibility, E = evidence saturation, C = domain
determinacy. Ordinal bands, no composite, anywhere. E is *derived* from the corpus
(rarefaction slope + diagnosticity counts), not self-reported — the certificate replaces
the vibes. Verbalized numeric confidence is documented as uncalibrated; do not present
R/E/C as probabilities.

---

## 8. Accumulation semantics (the wiki property)

- **Re-running is revision, not repetition.** Warm starts brief farms on known basins
  and point them at holes; the rarefaction curve resumes.
- **Tripwires are standing sensors.** Every falsification trigger and revisit-condition
  becomes a stored query the sentinel checks each run; fired → contested → blast radius.
  The map self-reports staleness.
- **Human atoms are first-class** and required engagement.
- **The instrument learns its optics.** Vantage-level yield stats (novel *verified* atoms
  per vantage) accumulate; future runs allocate the independence budget by measured yield.
- **Cross-question compounding.** Questions embed; new questions inherit the relevant
  neighborhood subgraph as prior context.

---

## 9. Consumer seams

### 9.1 dialectic-plugin v2 (the advocate)

dialectic-plugin v2 becomes ant-farm's first client — and its second sensor. The seam
is two-way: **seed, consume, compound** (amended 2026-07-05). A dialectic session is
not a detached tool that reads the map; it is an instrument pass that enriches it.
Changes:

- **Two-way seam (added 2026-07-05):**
  - *Seed* — a v2 session opens with a warm-start brief from the corpus: the view
    neighborhood of its question (same brief machinery as farm warm-starts). Prior
    basins, cruxes, and standing challenges are the session's starting terrain,
    never re-derived.
  - *Consume* — distill and forge as view consumers (below), unchanged.
  - *Compound* — at session end, the session's atoms harvest into the event log as
    a first-class vantage (`sensor: "model"`, advocate persona, session id as run).
    Claims, evidence, rebuttals, qualifications map from the sublation loop's output
    exactly as scout emissions do (the v1 marker vocabulary already maps: bridge →
    edge, rebuttal → rebuts/undercuts, support + licence → supports + warrant).
    Concessions land as status events with died-because records. Entailment merge
    dedups against the well; a re-found claim increments sightings — every advocacy
    session compounds the corpus instead of evaporating. Plan 4 implements this
    harvest against plan 2's emission schema and CLI; no new corpus machinery.
- **Deleted:** stop-hook loop (both implementations), dead `explorations`/`elevate_trigger`
  code, `serialize-trace.js` (schema-forced atoms make scraping obsolete), the broken
  `patterns/{domain}.md` references (files split for real), SKILL.md's contradictory
  R/E/C definitions and composite.
- **Kept and sharpened:** sublation/preservation/amputation (now Phase 2's in-farm
  protocol), distill and forge as **view consumers** — distill's refutatio uses the
  strongest surviving rival (a counter that fought for its life); forge's decision
  points are rival forks with died-because records; unresolved cruxes ship as dissent,
  never averaged. Promotion header-renaming becomes a script.
- **Skill files** (both repos): hub-and-spoke progressive disclosure; SKILL.md as thin
  router; per-pass files at 2–3k tokens; worked examples in `references/`; iron laws in
  the first 10 lines (primacy bias). Style gate, five rules: one sentence = one
  executable instruction; imperative/positive/present; emphasis by position, not caps;
  one concrete example over three adjectives; one term per concept. Enforced by a
  prose-reviewer pass over every rewritten file.

### 9.2 keel (the geometer)

[keel](https://github.com/AustinSalter/keel) asks whether activation geometry can
distinguish coherent multi-turn reasoning from degraded reasoning, without generating
text. ant-farm is a **corpus source** for keel — nothing more in v1.

**Design rule: instrument/measure independence.** ant-farm is optimized for coverage,
never for keel's metric — keel's evidence is credible precisely because its stimuli come
from a system with a different objective. Symmetrically, keel keeps non-ant-farm trace
sources: a measure validated only on sublation-shaped traces would make "damping =
coherence" near-tautological, since the sublation loop damps by construction.

**What the exhaust gives keel that it has never had:** N parallel traces on the *same
question*, stratified by family/persona/round — within-question variation with question
fixed effects. Vantage is the covariate set; keel's current corpus (four sessions, four
topics) confounds topic with coherence.

**Export contract** (per farm, written at Phase 7):

- `trace.jsonl` in keel's `traces/` schema (§4.5 field mapping), vantage manifest as
  `stats.json`.
- Outcome metadata: farm decision (CONCLUDE | CONCEDE | ELEVATE), degeneration-ledger
  state, verification stats.

**Label discipline.** CONCEDE is a dialectical outcome, not a structural label — a farm
that tracks its thesis and honestly abandons it is highly germane; never export it as
degraded. **Coherent-but-wrong** (keel's Sprint 2.6 gap) = CONCLUDE with a clean ledger
whose conclusion is later refuted by verified evidence on the map — exported as
`coherence_label: coherent_refuted`. All outcome labels are model-judged; geometry
validated against them alone measures agreement with LLM-as-judge — the thing keel
exists to replace. Which is why the primary offering is:

**Counterfactual generator** (deliverable: a small script over retained transcripts —
ground truth by construction, no judge):

- **shuffle** — permute turns (keel's existing negative control).
- **graft** — splice rounds from a sibling farm on the same question: same topic, same
  vocabulary, locally coherent, thesis-discontinuous. The hardest possible D2 probe.
- **persona-swap** — regenerate rounds k..n under a different persona mid-farm.

**Non-goal (v1):** keel does not gate, filter, rank, or score anything inside the
ant-farm pipeline. Wiring keel in before it validates against the counterfactual set
creates a closed loop — keel gating the traces that later validate keel. Deferred (§12).

---

## 10. Eval harness (in-scope, gates "done")

1. **Critic recall:** 6–10 fixture traces with planted flaws (broken warrant,
   non-diagnostic evidence counted as support, degenerating patch sequence, soft
   falsification trigger, buried contradiction); score blind-critic recall. v2 ships
   only if it beats a v1-style same-context critique baseline on the same fixtures.
2. **Certificate calibration:** questions with a hand-built reference consideration set
   (MRecall); check the estimator's unseen-mass prediction against held-out
   considerations; verify the correlation discount moves n_eff in the right direction
   when farms are deliberately same-family.
3. **Merge fidelity:** synthetic duplicate/paraphrase atoms; entailment clustering must
   merge paraphrases and separate genuine variants at the chosen threshold.

---

## 11. Cost profile

| Mode | Shape | Rough cost vs. dialectic v1 |
|---|---|---|
| `--lean` | 1 farm + blind critics, no rivals | ~1.5–2× |
| default | 3 farms (3 families) × ~3 rounds + critics + stitch | ~4–6× |
| `--saturate` | gap-directed spawning until certificate plateau or budget cap | open-ended, bounded by workflow budget + `/workflows` live token view |

Cost controls are the runtime's: per-agent token visibility, pause/stop without losing
completed work, resume with cached results.

---

## 12. Out of scope (v2.1+)

Walton scheme library; Neo4j; multi-provider model routing beyond what the workflow
runtime exposes; a web UI for the map (Obsidian render is the v1 map UI); automated
cross-question transfer beyond neighborhood retrieval; keel as an in-pipeline
coherence sensor (generation-free farm ranking, late-atom gating for the Phase 4
verification floor) — only after keel validates against the §9.2 counterfactual set.

## 13. Open questions

1. Entailment-clustering threshold: which model/method for "same consideration," and is
   the threshold per-question or global? (Eval §10.3 decides empirically. RESOLVED
   2026-07-04 for the default embed: 0.67, plan 1 merge-fidelity eval; per-question
   thresholds remain open.)
2. Family mix when only Anthropic models are available in the runtime — is persona+CoT
   diversity alone enough to claim n_eff > 1.5 per 3 farms? (Measure, then decide.)
3. Where human atoms enter: CLI command, Obsidian inbox note, or both?
4. License/positioning of ant-farm (the coverage-certificate method is publishable).
5. **Round-continuity ablation (added 2026-07-05, decide by A/B, not argument).** Two
   hypotheses about what carries a farm's reasoning between rounds:
   - *Accumulation-as-gradient (Austin's prior):* the session trajectory is optimizer
     state — momentum, unverbalized leads, the exact phrasing of earlier moves. Fresh
     context per round zeroes the velocity and keeps only the position; carry-over is
     what makes successive rounds sharper.
   - *Compression-as-hygiene (current design):* long contexts drift — self-anchoring,
     content-free patches, sycophancy toward one's own prior text. Farm-dir carryover
     (compressed state + critiques + atoms) keeps the position and sheds the drift.
   Test: same questions, same personas, two arms — (A) fresh scout per round with
   farm-dir carryover (as built); (B) one long-context scout running all rounds in a
   single agent call, same pass protocol, same emission schema. Both arms already
   export everything needed to score: per-farm view admissions, sightings earned,
   challenges survived after blind critique, degeneration-ledger state,
   CONCLUDE-gate outcomes, and retained transcripts for keel's coherence labels.
   Cheap to run once plan 2 lands — arm B is a prompt-level variant of the same
   workflow, not a second architecture. If B wins, continuity fidelity (not agent
   count) becomes the tuning knob; if A wins, the ledger evidence explains why.
