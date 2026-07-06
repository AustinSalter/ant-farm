# Sublation and Decision

Sublation opens every round: metabolize the standing critiques before you
expand. The decision closes it: CONTINUE | CONCLUDE | ELEVATE | CONCEDE.

## Disposition Per Critique

Read `critiques/*.json` in your farm directory. Every unaddressed finding gets
exactly one disposition, recorded in the sublation list:

- **accepted** — the finding is right. Change your state: revise the thesis,
  demote the evidence, drop the claim. Say what changed.
- **rebutted** — the finding is wrong. Emit a self-contained claim atom and a
  rebuts edge quoting the finding's text exactly. A rebuttal names why the
  finding fails, not why your thesis is nice.
- **qualified** — the finding is right about scope. Narrow the thesis to the
  domain where it holds and emit the qualified claim.

Silence is not a disposition. A finding you neither accepted, rebutted, nor
qualified stands against you at the CONCLUDE gate.

## Preservation Gate (Required)

Before deciding, answer three questions about your hypothesis under critique:

1. **What does it correctly identify?** — the sound content the critiques left
   standing.
2. **What does it correctly frame?** — the framing worth keeping even if the
   claim narrows.
3. **What must any revision retain?** — the non-negotiables.

If you cannot complete this, you have not understood your own hypothesis —
decide CONTINUE and target expansion at what you cannot answer. Carry forward
what the critique left standing — sublation preserves.

## Amputation Check (Run Before Deciding)

The failure mode: counters are acknowledged but change nothing. For each
standing rebut or undercut against your thesis, ask: did this change the
thesis, or was it acknowledged and set aside?

A med- or high-severity counter acknowledged without changing the thesis is an
amputation — the thesis is absorbing hits without adapting, which means it
sits at the wrong altitude. One or more amputations bar CONCLUDE. Take ELEVATE
if the evidence gate passes; otherwise CONTINUE, targeting the data that would
make the right altitude visible. No zombie claims: a claim the critique killed
gets excised, not carried forward beside its refutation.

## Ledger Honesty

Fill ledger_entry every round. novel_content=false when your patch added
nothing new — a restated thesis, a re-worded rebuttal, a defensive
qualification that concedes nothing. Two consecutive patches with
novel_content=false force ELEVATE or CONCEDE. The gate script checks the
ledger; a flattering entry delays the same verdict by one round. Lakatos: a
degenerating program predicts nothing new.

## Evidence Gate for ELEVATE

Elevating on thin evidence produces a guess, not a grounded reframe. Before
choosing ELEVATE, write the elevated hypothesis from evidence already in your
farm. If you cannot — if the right altitude is suspected but not yet visible
in what you have gathered — CONTINUE instead, and name in your compressed
state exactly what data would reveal the right altitude.

## Decision

| Decision | When | Required output |
|----------|------|-----------------|
| CONTINUE | Evidence gaps exist and are addressable with data | The specific data that resolves them, named in the compressed state |
| CONCLUDE | Thesis robust at the right altitude, no amputated counters | The bet + a high-severity falsification trigger |
| ELEVATE | Wrong altitude or amputated counters, and the elevated hypothesis is already visible in the evidence | The elevated hypothesis + what it preserves + what it resolves |
| CONCEDE | The thesis lost: a rival explains the evidence better, or the core claim is refuted and no elevation preserves anything worth keeping | died_because — the specific finding or evidence that killed it |

**CONCLUDE only when you can state:**
- The bet: "X over Y because mechanism Z."
- Falsification: a high-severity trigger on record — a specific, testable
  condition that would flip the thesis. Test it: would a false thesis survive
  this trigger? If yes, the trigger is soft and the gate will bounce you.
- No standing undercuts against your atoms, and a clean ledger. The script
  enforces all three; claim only what you can defend.

**ELEVATE requires:**
- The elevated hypothesis — what the original was reaching for.
- What it preserves from the original (the preservation gate's answers).
- What tension it resolves.
- Which amputated counter(s) the elevation integrates.

**CONCEDE is a contribution, not a failure.** A farm that tracks its
hypothesis honestly and abandons it when a rival wins hands the survey a
died-because record — the map renders it as a conceded position with its cause
of death. Fabricated survival corrupts the map; honest death improves it.

## Worked Example

Original hypothesis: "Stripe has better documentation and easier integration."
Standing critique: an undercut — documentation quality is copyable, so
adoption evidence cannot license a durable-advantage conclusion.

- Disposition: accepted. The counter is material and the thesis cannot absorb
  it unchanged — leaving the thesis as-is would be an amputation.
- Preservation gate: correctly identifies that developer experience drives
  adoption; correctly frames payments as infrastructure, not product; any
  revision must retain the developer-centric insight.
- Evidence gate: the elevated hypothesis is already visible — the bridged
  finding that connects the adoption evidence to the PayPal-founders anomaly.
- Decision: ELEVATE. Elevated hypothesis: "Developer experience is the wedge
  into financial infrastructure: companies choose payment APIs early, before
  procurement; once integrated, Stripe becomes merchant of record, compliance
  layer, and billing system, and switching costs compound — the moat is
  infrastructure lock-in, not documentation." Preserves: developer experience
  as the key lever. Resolves: why PayPal's founders would invest against their
  own company — they see an infrastructure play, not product competition.

## Adaptation notes (maintainer record — not instructions)

<!--
- CONCEDE is new in v2: v1 ran a single advocate with no rival farms, so a
  thesis could only continue, conclude, or elevate. Parallel farms make honest
  death a first-class outcome with a died_because record.
- v1's numeric ELEVATE evidence gate ("requires E ≥ 0.4") is rephrased
  qualitatively — E is system-derived and not visible to the scout. The
  operational test (can you write the elevated hypothesis from evidence in
  hand?) preserves the gate's intent.
- v1's CONCLUDE criteria gain the HIGH falsification trigger and standing-
  undercutter checks because v2's gate script enforces them (spec §5); v1
  relied on self-report.
- v1's amputation_check YAML block and decision output formats are replaced by
  the schema-forced ScoutRoundOutput emission; the stop-hook section and
  thesis-history.md mechanics are stripped.
-->

