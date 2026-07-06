# Critique Probes

Test whether the trace's hypothesis actually protects what it claims to
protect. The trace is an authorless document; attack the reasoning as found.

## Meta-Probes

Run all five against the framed hypothesis:

| Probe | Question | Failure mode |
|-------|----------|--------------|
| Contingency | Does this depend on something that could change? | Temporary mistaken for structural |
| Mechanism | Is the causal path missing? | Assertion without causation |
| Anomaly | Does counter-evidence go unaddressed? | Ignored disconfirmation |
| Model dependency | Have the model's assumptions stopped holding? | Outdated model |
| Implementation | Does this assume rational response? | Perverse or irrational response |

Each probe that fails becomes a finding. A probe that passes is not a finding;
do not pad the report.

## Rebutting vs Undercutting

Classify every finding (Pollock's distinction):

- **rebutting** — the claim is false. You attack the conclusion or its grounds:
  the fact is wrong, the data says otherwise, a rival explains it better.
- **undercutting** — the inference is unlicensed. The premises may be true,
  but the warrant connecting them to the conclusion fails: the sample does not
  generalize, the analogy breaks, the correlation has a confound.

The distinction decides what the farm must repair. A rebutted claim needs new
evidence or death; an undercut inference needs a new warrant — the old
evidence is fine. Misclassification sends the scout to fix the wrong thing.

**Warrant probe** — the highest-value attack. Find the strongest supports edge
in the trace and attack its warrant, not its grounds. Grounds are usually
checkable facts; the warrant is where unlicensed inference hides. "Voluntary
developer adoption indicates lower integration cost" — does adoption indicate
that, or does it indicate free credits and network defaults?

## Severity

Grade every finding low | med | high:

- **high** — the thesis cannot stand if this finding holds. The load-bearing
  warrant is broken, the core claim is refuted, or two load-bearing statements
  contradict each other.
- **med** — the thesis survives but narrows: a scope limit, a weakened support,
  an unpriced risk that changes the confidence a reader should have.
- **low** — real but peripheral: a weak citation, an overstated aside, an
  imprecision that does not touch the mechanism.

Grade against the thesis, not the sentence. A factual error in a throwaway
line is low even though it is clearly wrong; a subtle warrant gap in the main
inference is high even though the sentence reads well. Severity inflation
burns the farm's rounds on trivia; deflation lets a dead thesis conclude.

## Retrieval

Retrieve from the well collection (`uv run python -m antfarm query --collection
well --text "..."`) — the well includes contested and buried material the view
excludes. A buried rebuttal the trace never answered is a finding; the farm
does not get to outlive an unanswered attack by forgetting it.

## Fact-Check with Web Search

Verify or challenge the trace's key claims. Budget 2–3 searches per critique.

Search for:
- Disconfirming evidence for the strongest supporting claims.
- Recent developments that affect the contingency and mechanism probes.
- Expert opinions that contradict the hypothesis's framing.
- Data that resolves tensions the trace left open.

For any web-sourced finding, state the source and date in the finding's text —
the finding becomes a corpus atom and must stand alone. When new evidence
changes a probe outcome, report the original result and the revised result.

## Premortem

"It is 12 months from now and the thesis failed — write the history." Write
the failure history first, in your reasoning or a scratch file; then distill
it into one self-contained premortem sentence naming the mechanism of failure. That
sentence becomes a named risk the farm must answer or rebut. "The thesis might
be wrong" is not a premortem; "Enterprise buyers standardized on the
incumbent's bundled offering, so integration quality never got a purchase
decision to influence" is.

## Contradiction Sweep

Scan the trace for statement pairs that cannot both be true. The common form:
an early claim quietly narrowed later, with conclusions still drawn from the
broad version. Quote both statements exactly; the pair is one finding,
classified rebutting, severity graded by how load-bearing the broad version is.

## Evidence Challenge

For each piece of evidence the trace counts as support, ask: can you name a
rival hypothesis this evidence fits equally well? Name the rival in the
finding. Evidence consistent with every rival is non-diagnostic — it supports
nothing, whatever its strength. The
trace claiming it as support is a finding, classified undercutting: the
evidence is real, the supports inference is unlicensed.

## Worked Example

Trace hypothesis: "Stripe has better documentation and easier integration."

- Contingency probe fails: documentation quality can be copied; the advantage
  is contingent, presented as structural. Finding, undercutting, med.
- Mechanism probe fails: no causal path from better docs to durable advantage.
  Finding, undercutting, high — the load-bearing inference has no warrant.
- Anomaly probe fails: PayPal founders investing in Stripe is unexplained by
  the "better product" framing and the trace does not address it. Finding,
  rebutting (the framing, not the fact), med.
- Evidence challenge: "90% of YC companies use Stripe" is consistent with the
  rival "Stripe wins on default status and free credits, not integration
  quality" — non-diagnostic as stated. Finding, undercutting, med.
- Premortem: "Incumbent processors shipped equivalent APIs within two years
  and competed on price, because documentation quality was never a defensible
  moat." One sentence, self-contained, names the mechanism.

## Adaptation notes (maintainer record — not instructions)

<!--
- The severity scale and the rebutting/undercutting classification are v2
  additions required by the CritiqueReport schema; v1 findings were unclassed
  prose. The meta-probes, fact-check protocol, and search budget port intact.
- v1's domain-specific probe files (`patterns/{domain}.md`) were deleted by
  spec §9.1 as broken references; only the five general meta-probes port.
- v1's preservation gate, elevation test, and decision sections belong to the
  scout in v2 and live in `sublation-and-decision.md`; the critic reports
  findings and never decides for the farm.
- v1's `[WEB]` rationale tag and YAML output formats are replaced by the
  schema-forced CritiqueReport emission; the stop-hook section is stripped.
-->

