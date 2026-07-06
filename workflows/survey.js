export const meta = {
  name: 'survey',
  description: 'One ant-farm survey run: sentinel, framing, parallel farms with blind critique, verification floor, stitch, hole probing, materialize',
  phases: [
    { title: 'Setup', detail: 'bind question, allocate run id' },
    { title: 'Sentinel', detail: 'check standing tripwires (skipped on first run)' },
    { title: 'Framing', detail: 'surveyor: stasis, DISSOLVE, Zwicky field, rivals' },
    { title: 'Farms', detail: 'scout rounds with interleaved blind critique, gated decisions' },
    { title: 'Verify', detail: 'verification floor over novel atoms' },
    { title: 'Stitch', detail: 'ACH matrix, disagreement investigation, declaration' },
    { title: 'Holes', detail: 'hole-finder probes, optional gap wave' },
    { title: 'Materialize', detail: 'view, vault, keel exports, curator map, persona-swap' },
  ],
}

if (!args || !args.question) throw new Error('args.question is required')
if (!args.schemas || !args.schemas.scout_round) {
  throw new Error('args.schemas is required - run `uv run python -m antfarm schemas` ' +
    'and pass the parsed JSON (see .claude/skills/survey/SKILL.md)')
}

const S = args.schemas
const CORPUS = args.corpusDir || 'corpus'
const MODES = {
  lean: { farms: 1, maxRounds: 2, holeAttempts: 1, verifyCap: 4, gapWave: false },
  default: { farms: 3, maxRounds: 3, holeAttempts: 3, verifyCap: 12, gapWave: false },
  saturate: { farms: 3, maxRounds: 3, holeAttempts: 5, verifyCap: 24, gapWave: true },
}
const MODE = MODES[args.mode || 'default']
if (!MODE) throw new Error(`unknown mode: ${args.mode} (lean | default | saturate)`)
const PERSONAS = args.personas || [
  'a municipal procurement officer', 'a startup CFO', 'a graduate research assistant',
]
const FAMILIES = args.families || ['opus', 'sonnet', 'haiku']

// --- clerk bridge: the only way this script touches the corpus ---------------

const CLERK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'stdout', 'error'],
  properties: {
    ok: { type: 'boolean' },
    stdout: { type: 'string' },
    error: { type: ['string', 'null'] },
  },
}

async function cli(cmd, payload, label, phaseName) {
  const scratch = `/tmp/antfarm-${label.replace(/[^a-zA-Z0-9]+/g, '-')}.json`
  const steps = ['Execute this for the ant-farm survey pipeline, from the repository root.']
  if (payload !== undefined) {
    steps.push(
      `1. Write this JSON verbatim to ${scratch}:`,
      JSON.stringify(payload),
      `2. Run: uv run python -m antfarm ${cmd} --corpus ${CORPUS} --input ${scratch}`)
  } else {
    steps.push(`Run: uv run python -m antfarm ${cmd} --corpus ${CORPUS}`)
  }
  const r = await agent(steps.join('\n'), {
    agentType: 'clerk', label: `clerk:${label}`, phase: phaseName,
    effort: 'low', schema: CLERK_SCHEMA,
  })
  if (!r || !r.ok) {
    throw new Error(`antfarm ${cmd.split(' ')[0]} failed: ${r ? r.error : 'clerk returned nothing'}`)
  }
  return JSON.parse(r.stdout)
}

const q = (s) => JSON.stringify(s)  // shell-safe quoting for string flags

// --- prompts ------------------------------------------------------------------

const RETRIEVAL_NOTE = (collection) =>
  `Retrieval: from the repository root run\n` +
  `  uv run python -m antfarm query --corpus ${CORPUS} --collection ${collection} --text "..."\n` +
  `(returns [] before the first materialize).`

function sentinelPrompt(tripwires) {
  return [
    'Standing tripwires to check against the current state of the world.',
    'For each, search for developments and judge strictly whether its condition is met.',
    JSON.stringify(tripwires, null, 2),
  ].join('\n\n')
}

function surveyorPrompt(brief, sentinelNote) {
  return [
    `Frame this contested question for a survey: ${args.question}`,
    `Sentinel report: ${sentinelNote}`,
    `Warm-start brief (prior corpus state - engage it, do not re-derive it):`,
    JSON.stringify(brief, null, 2),
    RETRIEVAL_NOTE('view'),
  ].join('\n\n')
}

function scoutPrompt(farm, round, gateReasons) {
  return [
    `Farm ${farm.key}, round ${round} of ${MODE.maxRounds}.`,
    `Question: ${args.question}`,
    `Your hypothesis: ${farm.hypothesis_text}`,
    `Your persona: ${farm.persona}`,
    `Your farm directory: ${CORPUS}/farms/${RUN}/${farm.key}`,
    `Read turns.jsonl there for your prior rounds and critiques/*.json for the` +
    ` critic reports you must sublate. Read ONLY this farm's directory.`,
    gateReasons.length
      ? `Last round the gate blocked your decision. Reasons:\n- ${gateReasons.join('\n- ')}`
      : '',
    RETRIEVAL_NOTE('view'),
  ].filter(Boolean).join('\n\n')
}

function criticPrompt(farm, round) {
  return [
    `A third-party reasoning document on the question: ${args.question}`,
    `The document: ${CORPUS}/farms/${RUN}/${farm.key}/turns.jsonl (read it fully).`,
    `Critique round ${round}. Quote target_text exactly as written in the document.`,
    RETRIEVAL_NOTE('well'),
  ].join('\n\n')
}

function verifyPrompt(item) {
  return [
    `Independently verify this ${item.type} using sources OUTSIDE the survey corpus`,
    `(web search, primary documents). Confirm or refute; do not soften.`,
    `Text: ${item.text}`,
    `Return verified=true only with concrete corroborating evidence and a source.`,
  ].join('\n')
}

function stitcherPrompt(brief) {
  return [
    `Stitch these farms into a map for the question: ${args.question}`,
    `Score every evidence item against every hypothesis (quote texts exactly).`,
    `Investigate only disagreements between farms.`,
    JSON.stringify(brief, null, 2),
  ].join('\n\n')
}

function holePrompt(declaration, attempt) {
  return [
    `Attempt ${attempt + 1}: produce ONE consideration absent from this corpus,`,
    `or fail honestly (candidate=null). Question: ${args.question}`,
    `Current declaration: ${JSON.stringify(declaration)}`,
    RETRIEVAL_NOTE('view'),
    `The map pages live in ${CORPUS}/vault/ if it exists.`,
  ].join('\n\n')
}

function curatorPrompt(declaration, summary) {
  return [
    `Render MAP.md for the question: ${args.question}`,
    `Declaration: ${JSON.stringify(declaration, null, 2)}`,
    `Materialize summary: ${JSON.stringify(summary)}`,
    `Rendered node pages are in ${CORPUS}/vault/ - read a few for wikilink targets.`,
  ].join('\n\n')
}

function swapPrompt(pkg, persona) {
  return [
    `Persona-swap counterfactual. Below are the opening turns of a reasoning farm.`,
    `Regenerate the REMAINING iterations (${pkg.regen_iterations.join(', ')}) as if a`,
    ` different persona - ${persona} - had taken over from iteration ${pkg.start_iteration}.`,
    `Stay on the same question and hypothesis; change the vantage, not the topic.`,
    `Emit expand and compress turns (and sublate where you address prior critique)`,
    ` for each regenerated iteration.`,
    `Context turns:`,
    JSON.stringify(pkg.context, null, 2),
  ].join('\n')
}

// --- Phase: Setup ---------------------------------------------------------------

phase('Setup')
const setup = await cli(`run-new --question ${q(args.question)}`, undefined, 'run-new', 'Setup')
const RUN = setup.run
log(`run ${RUN} on question ${setup.question_id} (first_run=${setup.first_run}, mode=${args.mode || 'default'})`)

// --- Phase 0: Sentinel ------------------------------------------------------------

phase('Sentinel')
let sentinelNote = 'No standing tripwires were checked this run.'
if (!setup.first_run) {
  const tripwires = await cli('tripwires-list', undefined, 'tripwires-list', 'Sentinel')
  if (tripwires.length) {
    const report = await agent(sentinelPrompt(tripwires), {
      agentType: 'sentinel', label: 'sentinel', phase: 'Sentinel',
      schema: S.sentinel_report,
    })
    const fired = report ? report.checks.filter((c) => c.fired) : []
    for (const check of fired) {
      const res = await cli(`tripwire-fire --run ${RUN} --id ${check.tripwire_id}`,
        { evidence: check.evidence }, `fire-${check.tripwire_id}`, 'Sentinel')
      log(`tripwire ${check.tripwire_id} fired; ${res.affected.length} node(s) contested`)
    }
    sentinelNote = fired.length
      ? `${fired.length} tripwire(s) fired this run: ` +
        fired.map((c) => c.evidence).join(' | ')
      : `${tripwires.length} tripwire(s) checked; none fired.`
  }
}
if (args.stopAfter === 'sentinel') {  // spec §5: --sentinel-only
  return { run: RUN, question_id: setup.question_id, sentinel: sentinelNote }
}

// --- Phase 1: Framing --------------------------------------------------------------

phase('Framing')
const warmBrief = await cli('brief', undefined, 'brief', 'Framing')
const framing = await agent(surveyorPrompt(warmBrief, sentinelNote), {
  agentType: 'surveyor', label: 'surveyor', phase: 'Framing', schema: S.framing,
})
if (!framing) throw new Error('surveyor agent failed')
const framed = await cli(`harvest-framing --run ${RUN}`, framing, 'harvest-framing', 'Framing')
if (framing.dissolve.dissolved) {
  log(`DISSOLVE at framing: ${framing.dissolve.diagnosis}`)
  return {
    dissolved: true, at: 'framing', run: RUN,
    diagnosis: framing.dissolve.diagnosis,
    replacement_question: framing.dissolve.replacement_question,
  }
}
if (args.stopAfter === 'framing') {  // spec §5: --frame-only
  return { run: RUN, question_id: setup.question_id, sentinel: sentinelNote,
           rivals: framed.rivals }
}
const farms = framed.rivals.slice(0, MODE.farms).map((rival, i) => ({
  key: String.fromCharCode(65 + i),
  hypothesis_id: rival.id,
  hypothesis_text: rival.text,
  persona: PERSONAS[i % PERSONAS.length],
  family: FAMILIES[i % FAMILIES.length],
}))
for (const farm of farms) {
  await cli(
    `farm-init --run ${RUN} --farm ${farm.key} --hypothesis-id ${farm.hypothesis_id}` +
    ` --hypothesis-text ${q(farm.hypothesis_text)} --persona ${q(farm.persona)}` +
    ` --family ${farm.family}`,
    undefined, `farm-init-${farm.key}`, 'Framing')
}
log(`${farms.length} farm(s): ` +
  farms.map((f) => `${f.key}=${f.family}/${f.persona}`).join(', '))

// --- Phases 2+3: Farms (scout rounds interleaved with blind critique) -------------

phase('Farms')
async function runFarm(farm) {
  let gateReasons = []
  for (let round = 1; round <= MODE.maxRounds; round++) {
    const out = await agent(scoutPrompt(farm, round, gateReasons), {
      agentType: 'scout', model: farm.family,
      label: `scout:${farm.key}:r${round}`, phase: 'Farms', schema: S.scout_round,
    })
    if (!out) {
      await cli(`farm-outcome --run ${RUN} --farm ${farm.key} --decision ELEVATE`,
        undefined, `outcome-${farm.key}`, 'Farms')
      return { farm: farm.key, decision: 'ELEVATE', reasons: ['scout agent failed'] }
    }
    const harvested = await cli(
      `harvest-scout --run ${RUN} --farm ${farm.key} --round ${round}` +
      ` --family ${farm.family} --persona ${q(farm.persona)}`,
      out, `harvest-${farm.key}-r${round}`, 'Farms')
    if (harvested.rejected.length || harvested.unresolved.length) {
      log(`farm ${farm.key} r${round}: ${harvested.rejected.length} atom(s) rejected, ` +
        `${harvested.unresolved.length} edge(s) unresolved`)
    }
    const finalRound = round === MODE.maxRounds
    const gate = await cli(
      `gate --run ${RUN} --farm ${farm.key}${finalRound ? ' --final-round' : ''}`,
      out, `gate-${farm.key}-r${round}`, 'Farms')
    if (gate.decision !== 'CONTINUE') {
      await cli(
        `farm-outcome --run ${RUN} --farm ${farm.key} --decision ${gate.decision}` +
        (out.died_because ? ` --died-because ${q(out.died_because)}` : ''),
        undefined, `outcome-${farm.key}`, 'Farms')
      return { farm: farm.key, decision: gate.decision, forced: gate.forced,
               reasons: gate.reasons }
    }
    gateReasons = gate.reasons
    const critique = await agent(criticPrompt(farm, round), {
      agentType: 'blind-critic', label: `critic:${farm.key}:r${round}`,
      phase: 'Farms', schema: S.critique_report,
    })
    if (critique) {
      await cli(
        `harvest-critique --run ${RUN} --farm ${farm.key} --round ${round}`,
        critique, `critique-${farm.key}-r${round}`, 'Farms')
    }
  }
  // unreachable: the gate never returns CONTINUE on the final round
  return { farm: farm.key, decision: 'ELEVATE', reasons: ['loop exhausted'] }
}

const outcomes = (await parallel(farms.map((farm) => () => runFarm(farm)))).filter(Boolean)
log('farm outcomes: ' + outcomes.map((o) => `${o.farm}=${o.decision}`).join(', '))

// --- Phase 4: Verification floor ---------------------------------------------------

phase('Verify')
const queue = await cli('verification-queue', undefined, 'verification-queue', 'Verify')
const toVerify = queue.slice(0, MODE.verifyCap)
if (queue.length > toVerify.length) {
  log(`verification capped at ${MODE.verifyCap} of ${queue.length} queued atoms`)
}
const verifications = (await parallel(toVerify.map((item) => () =>
  agent(verifyPrompt(item), {
    label: `verify:${item.id}`, phase: 'Verify', schema: S.verification_result,
  }).then((v) => v && { atom_id: item.id, verified: v.verified,
                        evidence: v.evidence, source: v.source })
))).filter(Boolean)
if (verifications.length) {
  const verified = await cli(`harvest-verify --run ${RUN}`, verifications,
    'harvest-verify', 'Verify')
  log(`verification floor: ${verified.verified.length}/${verifications.length} upgraded`)
}

// --- Phase 5: Stitch ----------------------------------------------------------------

phase('Stitch')
let declaration = null
let dissolvedAtStitch = null
async function runStitch(label) {
  const brief = await cli(`stitch-brief --run ${RUN}`, undefined, `stitch-brief-${label}`, 'Stitch')
  const stitch = await agent(stitcherPrompt(brief), {
    agentType: 'stitcher', label: `stitcher-${label}`, phase: 'Stitch', schema: S.stitch,
  })
  if (!stitch) return
  const res = await cli(`harvest-stitch --run ${RUN}`, stitch, `harvest-stitch-${label}`, 'Stitch')
  declaration = res.declaration
  if (stitch.dissolve.dissolved) {
    dissolvedAtStitch = {
      diagnosis: stitch.dissolve.diagnosis,
      replacement_question: stitch.dissolve.replacement_question,
    }
  }
}
await runStitch('1')

// --- Phase 6: Holes and the gap-directed spawn decision -----------------------------

phase('Holes')
const holes = []
let failureStreak = 0
for (let attempt = 0; attempt < MODE.holeAttempts; attempt++) {
  const hf = await agent(holePrompt(declaration, attempt), {
    agentType: 'hole-finder', label: `hole-finder:${attempt + 1}`,
    phase: 'Holes', schema: S.hole_finder,
  })
  if (!hf || !hf.candidate) { failureStreak++; continue }
  const probed = await cli('probe', { text: hf.candidate }, `probe-${attempt + 1}`, 'Holes')
  if (probed.novel) { holes.push(hf.candidate); failureStreak = 0 } else { failureStreak++ }
}
log(`hole-finder: ${holes.length} hit(s), closing failure streak ${failureStreak}`)
if (holes.length) {
  const holeAtoms = await cli(
    `harvest-atoms --run ${RUN} --farm hole-finder --persona hole-finder`,
    { atoms: holes.map((text) => ({ type: 'claim', text })), edges: [] },
    'harvest-holes', 'Holes')
  if (MODE.gapWave && (!budget.total || budget.remaining() > 100_000)) {
    const gapFarms = holes.slice(0, 2).map((text, i) => ({
      key: `G${i + 1}`,
      hypothesis_id: holeAtoms.atom_ids[i],
      hypothesis_text: text,
      persona: PERSONAS[(farms.length + i) % PERSONAS.length],
      family: FAMILIES[(farms.length + i) % FAMILIES.length],
    }))
    for (const farm of gapFarms) {
      await cli(
        `farm-init --run ${RUN} --farm ${farm.key} --hypothesis-id ${farm.hypothesis_id}` +
        ` --hypothesis-text ${q(farm.hypothesis_text)} --persona ${q(farm.persona)}` +
        ` --family ${farm.family}`,
        undefined, `farm-init-${farm.key}`, 'Holes')
    }
    log(`gap wave: spawning ${gapFarms.length} farm(s) briefed at the largest holes`)
    const gapOutcomes = (await parallel(gapFarms.map((farm) => () => runFarm(farm))))
      .filter(Boolean)
    outcomes.push(...gapOutcomes)
    await runStitch('2')
  }
}

// --- Phase 7: Materialize ------------------------------------------------------------

phase('Materialize')
const summary = await cli(`materialize --run ${RUN}`, undefined, 'materialize', 'Materialize')
log(`view=${summary.view_size} pages=${summary.pages} ` +
  `tripwires+${summary.tripwires_registered} farms=${summary.farms_exported.join(',')}`)

const curated = await agent(curatorPrompt(declaration, summary), {
  agentType: 'curator', label: 'curator', phase: 'Materialize', schema: S.curator,
})
if (curated) await cli('map-write', curated, 'map-write', 'Materialize')

// persona-swap counterfactual over the first farm that ran multiple iterations
const swapFarm = farms[0]
if (swapFarm) {
  const pkg = await cli(
    `persona-swap-prepare --run ${RUN} --farm ${swapFarm.key} --start-iteration 2`,
    undefined, 'persona-swap-prepare', 'Materialize')
  if (pkg.eligible) {
    const altPersona = PERSONAS.find((p) => p !== swapFarm.persona) || 'a careful auditor'
    const regen = await agent(swapPrompt(pkg, altPersona), {
      label: 'persona-swap', phase: 'Materialize', schema: S.persona_swap,
    })
    if (regen) {
      await cli(
        `persona-swap-write --run ${RUN} --farm ${swapFarm.key} --start-iteration 2`,
        regen, 'persona-swap-write', 'Materialize')
      log(`persona-swap counterfactual written for farm ${swapFarm.key}`)
    }
  }
}

return {
  run: RUN,
  question_id: setup.question_id,
  farms: outcomes,
  declaration,
  holes,
  view_size: summary.view_size,
  transcripts: summary.farms_exported,
  ...(dissolvedAtStitch ? { dissolved: true, at: 'stitch', ...dissolvedAtStitch } : {}),
}
