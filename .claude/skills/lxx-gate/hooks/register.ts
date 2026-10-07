import type { EngineInterface, Register } from 'claude-code'

// The verdict is `lxx stamp --brief`'s, never this file's: the hash the
// commit hooks compare lives in .claude/tools/lxx, and a second copy here
// would be the drift that harness exists to prevent.
const LXX = '.claude/tools/lxx'
// Edits made outside the session (Emacs) raise no event, so poll as well.
const POLL_MS = 30_000

// The repository root once session.start has found the harness there.
let root: string | undefined
let running = false

async function refresh($: EngineInterface): Promise<void> {
  if (root === undefined || running) return
  running = true
  try {
    const { exitCode, stdout } = await $.process.run(
      [`${root}/${LXX}`, 'stamp', '--brief'], { cwd: root, timeoutMs: 10_000 })
    const line = stdout.trim().split('\n')[0]
    $.ui.status(line ? `${exitCode === 0 ? '✓' : '✗'} ${line}` : undefined)
  } catch {
    $.ui.status('✗ lxx: stamp check failed')
  } finally {
    running = false
  }
}

async function locate($: EngineInterface, cwd: string): Promise<void> {
  try {
    const st = await $.fs.stat(`${cwd}/${LXX}`)
    root = st.kind === 'file' ? cwd : undefined
  } catch {
    root = undefined
  }
}

export const register: Register = on => {
  root = undefined
  running = false

  on('session.start', async ($, e, next) => {
    const done = await next(e)
    await locate($, e.cwd)
    if (root !== undefined) {
      await refresh($)
      $.clock.every(POLL_MS, () => void refresh($))
    }
    return done
  })

  // Any of these may have written a source (Edit, Write, a sed in Bash) or
  // the stamp (lxx test): look again once it has run.
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (e.tool === 'Edit' || e.tool === 'Write' || e.tool === 'Bash'
        || e.tool === 'NotebookEdit') {
      await refresh($)
    }
    return ran
  }).catch(($, e, next) => next(e))   // a status line never blocks a tool
}
