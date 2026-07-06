# Expansion Pass

Two jobs: (1) select the right frame, (2) gather evidence within it. Emit atoms
and edges the moment you find them.

## Phase 1: Frame Selection (Do First)

Before searching, answer these:

**What is this hypothesis trying to protect?**
Not what it claims — what concern motivates it.
- "Pass on this investment" → capital preservation
- "Adopt probable cause" → student privacy rights
- "Enter this market" → growth / competitive position

**What altitude should we operate at?**

| Level | Symptom | Example |
|-------|---------|---------|
| TOO GRANULAR | Accurate details, no pattern | "Their API docs are better" |
| RIGHT LEVEL | Mechanism + transferability | "Developer adoption creates compounding switching costs" |
| TOO ABSTRACT | Pattern named, no mechanism | "They have network effects" |
| TOO ABSTRACT | Action prescribed, no causal path | "We should vertically integrate to control costs" (integrate what? through what mechanism? why does ownership reduce costs here?) |

**Altitude test for action-prescribing hypotheses**: if the hypothesis
prescribes an action ("build X", "invest in Y", "ban Z"), list the causal steps
between the action and the claimed outcome:

```
Action: [what the hypothesis prescribes]
Step 1: [first thing that happens]
Step 2: [what that causes]
Step 3: [how that produces the claimed outcome]
```

If you cannot list 3+ concrete steps, the hypothesis is TOO ABSTRACT even if it
sounds specific. "Vertically integrate" sounds like a strategy but skips the
causal chain: acquire supplier → ??? → lower costs. The missing step is the
altitude problem. Note the missing step in your compressed state.

## Phase 2: Guided Search

Gather evidence within the selected frame. Retrieve from the view collection
only: `uv run python -m antfarm query --collection view --text "..."`. Then
search the open web for what your persona would not think to look for: sources
arguing from the opposing frame.

**Search targets, in priority order:**

1. **Supporting evidence** — what confirms the frame?
2. **Challenging evidence** — what contradicts it?
3. **Second-order effects** — "if X, then Y, then Z"
4. **Anomalies** — smart people on the other side, unexplained data

**Pursue anomalies abductively.** An observation your hypothesis cannot explain
is the highest-value search target in the pass. Ask "what would have to be true
for this anomaly to make sense?", then search for that. The Stripe example
below turns on one anomaly pursued this way.

**Emit findings as atoms and edges:**

| Finding | Emission |
|---------|----------|
| Concrete fact, metric, quote | evidence atom (strength 1–5) |
| Evidence that licenses your hypothesis | supports edge + warrant (the rule licensing the inference, stated so it can be attacked) |
| Argument that a claim is false | claim atom + rebuts edge |
| Argument that an inference is unlicensed | claim atom + undercuts edge |
| Two findings that contradict each other | tension atom, edges to both |
| Source that narrows a claim without contradicting it | qualifies edge |
| Finding that exists only by combining sources A and B | claim atom + bridges edges to both — present in neither alone |
| Claim that presupposes another | depends_on edge |

Write every atom self-contained: no pronouns, no "this shows"; a reader with
zero context understands it. Edges to existing material quote the target's
text exactly.

## Reading Sources

Read each source's whole argument; do not skim for quotable fragments. As you
read, be alert to four things:

**Position.** Where does this source sit? Primary (original assertion, original
data, first to say it), downstream (restating someone else's claim), critique
(arguing against a claim you've seen), synthesis (combining prior claims into a
new framing). Five downstream sources are one source. One primary against four
downstream is not "outnumbered." Record position in the strength rating:
observed data with citation 5, credible report 4, pattern inference 3, general
knowledge 2, speculation 1 — and a downstream restatement takes at most 3,
whatever its original scores.

**Load-bearing parts.** What does the argument actually rest on? Often the
buried qualifier, the conceded footnote, the aside that constrains the headline
claim. Query-relevant ≠ load-bearing. Notice the part the author would lose
sleep over if it were wrong.

**Incentive.** Who benefits if this is believed? Be specific: "vendor selling
X," "researcher whose prior work depends on Y." Aligned incentive makes a
source's load-bearing claims deserve harder reading, not dismissal. A claim
that survives an opposing-incentive source is stronger.

**Stitch points.** When this source connects to one you've already read —
bridges a gap, resolves a tension, sharpens a contradiction — emit the bridges
edge as it happens. The non-obvious findings live in the joins, not in any
single source. If you have emitted no bridges edges by the last source, you
read sources in parallel but did not read them together — reread your atoms
for joins before the pass ends.

**Reading heuristics:**
- Read in the order fetched. Earlier sources frame later ones.
- Carry your reasoning across sources; never restart it per source.
- A source that shifts nothing is worth one line; a source that shifts the frame is worth a paragraph.
- If every source agrees, ask what they all share that might be wrong. Consensus is a position too.
- Budget 3–5 fetches per expansion pass.
- Ground evidence atoms in their source: name the source and date for web findings; say so when a fact comes from prior knowledge only.
- Note what you searched for but could not find — an absence is information.

## Do not

- Conclude or decide (the decision pass does that)
- Search outside the frame (reframe first if the frame is wrong)
- Ignore counter-evidence (seek it — search target 2, Challenging evidence)
- Skip frame selection (everything downstream inherits the frame)

## Worked Example

**Hypothesis:** "Stripe has better documentation and easier integration."

**Frame selection:** protecting an investment in a payments company; altitude
TOO GRANULAR (features, not structure) — should be "developer adoption →
switching costs → infrastructure moat"; domain: infrastructure.

**Guided search, emitted as atoms and edges:**

- evidence (strength 5): "Stripe processes over $1T annually and is used by over 90% of Y Combinator companies." — supports edge to the hypothesis, warrant: "broad voluntary developer adoption indicates lower integration cost than alternatives."
- claim: "PayPal, Adyen, and Braintree all offer payment APIs; documentation quality is copyable by incumbents." — undercuts edge to the supports inference above: adoption evidence cannot license a durable-advantage conclusion if the advantage is copyable.
- evidence (strength 4): "PayPal founders Thiel and Musk invested in Stripe." — an anomaly: unexplained by the "better product" frame. Pursued abductively: what would make investing against your own company rational?
- tension: "Stripe's advantage being copyable documentation contradicts PayPal founders investing against their own company; either the spend is irrational or the moat is not the documentation."
- claim (bridges the adoption evidence and the investor anomaly): "Stripe's moat is infrastructure lock-in after integration — merchant of record, compliance, billing logic — not documentation quality; documentation is the wedge, not the moat."
- Open threads for the next round, carried in the compressed state: actual switching costs post-integration; churn rates for integrated customers.

## Adaptation notes (maintainer record — not instructions)

<!--
- v1 marker vocabulary maps to edges per MARKERS.md: `[BRIDGE: A→B]` →
  bridges edge; `[COUNTER]`/`[CONTRADICTS: A]` → rebuts or undercuts edge;
  `[QUALIFIES: A]` → qualifies edge; `[TENSION]` → tension atom; `[EVIDENCE]` →
  evidence atom with strength; `[INSIGHT]` → claim atom; support with a stated
  licence → supports edge + warrant. Position/incentive markers fold into the
  evidence strength rating rather than surviving as markers.
- v1's `[THREAD]`/`[QUESTION]` markers have no atom type; open threads carry
  forward inside the compressed state's live risks instead.
- v1's domain pattern files (`patterns/{domain}.md`) were deleted by spec §9.1
  as broken references; the domain table and per-domain probe lists are not
  ported. Frame selection keeps the protect/altitude questions, which did the
  real work.
- v1's YAML output format is replaced by the schema-forced ScoutRoundOutput
  emission; no output-format section is ported.
-->

