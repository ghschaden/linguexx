import { expect, mock, test } from 'claude-code/testing'

const ROOT = '/repo'

function world(on: any, answers: { exitCode: number; stdout: string }[], harness = true) {
  const status: (string | undefined)[] = []
  const runs: (readonly string[])[] = []
  on('fs.stat', ($: any, e: any) => {
    if (harness && e.path === `${ROOT}/.claude/tools/lxx`) {
      return { value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }
    }
    return { deny: 'ENOENT' }
  })
  on('process.run', ($: any, e: any) => {
    runs.push(e.argv)
    const a = answers[Math.min(runs.length - 1, answers.length - 1)]!
    return { value: { ...a, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.status', ($: any, e: any) => { status.push(e.text); return { value: undefined } })
  on('session.start', ($: any, e: any) => ({ cwd: e.cwd }))
  return { status, runs }
}

test('shows the brief stamp at start, marked by its exit code', async ($, on) => {
  mock.clock(on)
  const w = world(on, [{ exitCode: 1, stdout: 'suite STALE: linguexx.sty\n' }])
  await $.session.start({ cwd: ROOT, surface: 'terminal', isInteractive: true })
  expect(w.runs[0]).toEqual([`${ROOT}/.claude/tools/lxx`, 'stamp', '--brief'])
  expect(w.status.at(-1)).toBe('✗ suite STALE: linguexx.sty')
})

test('polls, so an edit made outside the session shows up', async ($, on) => {
  const clock = mock.clock(on)
  const w = world(on, [{ exitCode: 1, stdout: 'suite STALE: rtl.tex\n' },
                       { exitCode: 0, stdout: 'suite green (suite, 10-07 12:00)\n' }])
  await $.session.start({ cwd: ROOT, surface: 'terminal', isInteractive: true })
  await clock.advance(30_000)
  expect(w.status.at(-1)).toBe('✓ suite green (suite, 10-07 12:00)')
})

test('stays silent outside a linguexx checkout', async ($, on) => {
  mock.clock(on)
  const w = world(on, [{ exitCode: 0, stdout: 'x' }], false)
  await $.session.start({ cwd: ROOT, surface: 'terminal', isInteractive: true })
  expect(w.runs.length).toBe(0)
  expect(w.status.length).toBe(0)
})
