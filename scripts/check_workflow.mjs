// Parses workflows/survey.js the way the Workflow runtime does: body of an
// async function with the runtime globals in scope. Top-level return/await
// are legal there; plain `node --check` would reject them.
import { readFileSync } from 'node:fs'

const src = readFileSync('workflows/survey.js', 'utf8').replace(/^export\s+/m, '')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log',
  'budget', 'workflow', src)
console.log('workflow syntax ok')
