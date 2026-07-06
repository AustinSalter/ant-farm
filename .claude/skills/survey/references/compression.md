# Compression Pass

Convergent synthesis. Distill the round to decision-relevant state: one
compressed_state paragraph plus confidence_r and confidence_c.

## The Compressed-State Paragraph

One paragraph, three obligations, in order:

1. **Your thesis** — the hypothesis as it stands after this round, stated
   self-contained: a reader with zero context understands what is claimed.
2. **Its strongest support** — the single best-warranted line of evidence.
   Name the evidence and the warrant, not just the conclusion.
3. **Its live risks** — the standing counters, unresolved tensions, and open
   threads the next round must face. Name each risk; "some uncertainty
   remains" is not a risk.

The paragraph is the farm's continuity: the next round's scout reads it cold.
Write it for that reader.

## Before Compressing: Count the Evidence Honestly

1. **Group sources by position before counting.** N downstream restatements of
   one primary claim are one piece of evidence, not N.
2. **Bridged findings outrank single-source findings.** A claim resting on a
   bridges edge that holds is more compelling than three sources independently
   saying the same thing.
3. **Aligned-incentive primary sources need a non-aligned corroborator** before
   their load-bearing claims count as strong support.
4. **Validate each insight against its evidence.** A claim whose supporting
   evidence atoms sit at strength 1–2 (general knowledge, speculation) is an
   evidence gap — name it as a live risk.
5. **Rebuttals and undercuts weaken what they hit.** A supports edge whose
   warrant carries a standing undercut is not your strongest support.
6. **Unresolved tensions carry forward.** A tension you cannot resolve this
   round goes into live risks, never silently dropped.

## Confidence: Two Bands, Two Questions

Report confidence_r and confidence_c as ordinal bands: low, med, high. Never
report numbers or probabilities. E (evidence saturation) is derived by the
system from the corpus — never self-report it.

### R — Defensibility: Can this survive scrutiny?

R is a gate, not a score. A broken warrant in the chain means the conclusion
does not follow, regardless of evidence volume. High evidence cannot compensate
for low R. Fix reasoning before gathering more evidence.

- **high** — every load-bearing inference has a stated warrant with no standing
  undercut; the critique found nothing this round that changed the thesis.
- **med** — the chain holds but at least one warrant is untested or one
  material counter is answered only partially.
- **low** — a load-bearing warrant is broken or a material counter stands
  unanswered. State in the compressed state what would repair it.

### C — Domain Determinacy: What certainty does the domain permit?

C measures how much certainty the domain allows, independent of your argument.
C reflects outcome variance, not argument quality — a brilliant argument about
an unpredictable domain still gets low C, and sound reasoning does not make
geopolitics predictable, so C must not track R.

C is discovered, not optimized. If your C band drifts upward across rounds
without new evidence about the domain itself, that is motivated reasoning.
More rounds do not reduce ontological uncertainty.

| Band | Domain profile | Example |
|------|---------------|---------|
| low | Geopolitics, multi-decade timelines, many actors with veto power, precedents that do not bind, unknown adoption inflections | "Will sovereign AI programs succeed over 15 years?" |
| med | Established markets with known dynamics but genuine strategic unknowns; historical patterns provide grounding and key variables are observable | "Will this acquisition generate synergies within 3 years?" |
| high | Well-understood mechanisms, bounded outcomes, strong precedent; physics, math, settled economics. Rare in contested questions. | "Will doubling server capacity reduce latency?" |

Self-check: high C on a geopolitical, multi-stakeholder, or 10+ year question
requires an explicit justification of why this domain is more predictable than
it appears. The default for wicked problems is low.

C drives how the claim is held downstream (act on it / hold provisionally with
a release condition / best available frame), never whether the farm stops.

## Saturation: Ask, Do Not Score

E is computed by the system, but the questions behind it shape your decision
input. Answer them into the live-risks clause:

- What is the strongest piece of evidence I have not looked for?
- If I found it, how much would it change the thesis?
- Am I seeing the same patterns repeated, or new patterns each round?

Same patterns repeating and no productive thread left is saturation evidence;
name it. A specific unexplored thread with high expected impact is the
opposite; name that instead — it is the next round's search target.

## Handoff

Compression sets state; the decision (CONTINUE | CONCLUDE | ELEVATE | CONCEDE)
follows its own protocol in `sublation-and-decision.md`. Do not decide here.

## Worked Example

Compressed state after the Stripe expansion round:

"Stripe's durable advantage is infrastructure lock-in after integration —
merchant of record, compliance, and billing logic — with developer experience
as the adoption wedge rather than the moat. Strongest support: over 90% YC
adoption plus platform expansion (Connect, Atlas, Radar), warranted by the rule
that voluntary developer adoption followed by product-surface expansion
indicates compounding switching costs. Live risks: post-integration switching
costs are asserted, not yet measured (no churn or migration-cost data — the
strongest unexamined evidence); the documentation-quality claim remains
copyable by incumbents and cannot carry support on its own."

confidence_r: med (the lock-in warrant is coherent but its key evidence is
still strength-3 inference). confidence_c: med (established market, observable
variables, genuine strategic unknowns).

## Adaptation notes

- v1's numeric 0.0–1.0 confidence scales, per-cycle update formulas
  (R/E deltas, caps), and the R/E/C composite are deleted per spec §9.1;
  R and C survive as ordinal bands with the same underlying questions.
- v1's E self-assessment and E-driven termination thresholds (deltas,
  0.6/0.7 cutoffs) are deleted: E is derived by the system from the corpus.
  The saturation questions survive as prose input to the decision.
- v1's C calibration anchor table (six numeric ranges) compresses to the
  three-band table above; the 0.7+/0.5–0.7/<0.5 memo-tone table survives as
  the one-line "how the claim is held" rule.
- v1's decision table and termination signals move to
  `sublation-and-decision.md`; v1's YAML output format is replaced by the
  schema-forced ScoutRoundOutput emission; the stop-hook section is stripped.
