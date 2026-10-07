import { expect, mock, test } from 'claude-code/testing'

import { fit, pngSize } from '../hooks/register'

// A PNG header for a 721 x 1223 image: signature, IHDR length and type,
// width, height -- all pngSize reads.
function header(width: number, height: number): string {
  const b = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13,
             0x49, 0x48, 0x44, 0x52]
  for (const v of [width, height]) b.push((v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255)
  b.push(8, 6, 0, 0, 0)
  const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  let s = ''
  for (let i = 0; i < b.length; i += 3) {
    const n = (b[i]! << 16) | ((b[i + 1] ?? 0) << 8) | (b[i + 2] ?? 0)
    s += A[(n >> 18) & 63]! + A[(n >> 12) & 63]! + A[(n >> 6) & 63]! + A[n & 63]!
  }
  return s
}

test('reads the size off a PNG header, and nothing off anything else', () => {
  expect(pngSize(header(721, 1223))).toEqual({ width: 721, height: 1223 })
  expect(pngSize(SMALL)).toEqual({ width: 8, height: 4 })
  expect(pngSize('aGVsbG8gd29ybGQgdGhpcyBpcyBub3QgYSBwbmc=')).toBeUndefined()
})

test('fits the picture by its aspect ratio, narrowing when rows run out', () => {
  // wide: limited by the columns
  expect(fit({ width: 800, height: 200 }, { columns: 100, rows: 40 }))
    .toEqual({ columns: 100, rows: 13 })
  // tall: limited by the rows, and narrowed to keep the shape
  expect(fit({ width: 721, height: 1223 }, { columns: 100, rows: 40 }))
    .toEqual({ columns: 47, rows: 40 })
})

const PNG = '/repo/.claude/.state/build/png/case-p1.png'
// a whole 8 x 4 PNG: the engine checks an Image's bytes, so a header will not do
const SMALL = 'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAECAYAAACzzX7wAAAAEklEQVR4nGP4z8DwHx9moL0CAHD0P8F+ACg+AAAAAElFTkSuQmCC'

test('a .png Claude reads is what the pane shows', async ($, on) => {
  mock.clock(on)
  const opened: string[] = []
  on('session.start', ($: any, e: any) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: undefined }))
  on('ui.open', ($: any, e: any) => { opened.push(e.id); return { value: undefined } })
  on('fs.read', () => ({ value: { base64: SMALL } }))
  on('tool.call', { tool: 'Read' }, () => ({ result: { type: 'image' }, text: '' }) as any)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })

  await $.tool.call({ tool: 'Read', tool_use_id: 't1', file_path: PNG } as any)
  expect(opened).toContain('lxx-render')

  const ui = await $.ui.mount({ plugin: 'lxx-render', surface: 'terminal',
    component: 'Pane', requestId: 'lxx-render', props: {} } as any)
  expect(await ui.find({ type: 'Image' })).toBeDefined()
  expect((await ui.find({ type: 'Markdown' }))?.text).toContain(`file://${PNG}`)
  await ui.unmount()
})

test('`lxx png` shows the last page it wrote; other commands show nothing', async ($, on) => {
  mock.clock(on)
  const reads: string[] = []
  on('session.start', ($: any, e: any) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: undefined }))
  on('fs.read', ($: any, e: any) => { reads.push(e.path); return { value: { base64: SMALL } } })
  const out = '/r/png/a-p1.png  721x1223px  (page 1 @ 150dpi)\n/r/png/a-p2.png  721x1223px  (page 2 @ 150dpi)\n'
  on('tool.call', { tool: 'Bash' }, ($: any, e: any) =>
    ({ result: { stdout: '', stderr: '' }, text: e.command.includes('png') ? out : '/r/x.png  1x1px' }) as any)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })

  await $.tool.call({ tool: 'Bash', tool_use_id: 't0', command: 'ls /r' } as any)
  const pane = { plugin: 'lxx-render', surface: 'terminal', component: 'Pane',
                 requestId: 'lxx-render', props: {} } as any
  let ui = await $.ui.mount(pane)
  expect(await ui.find({ type: 'Image' })).toBeUndefined()
  await ui.unmount()

  await $.tool.call({ tool: 'Bash', tool_use_id: 't1',
                      command: '.claude/tools/lxx png build/a.pdf --crop' } as any)
  ui = await $.ui.mount(pane)
  expect((await ui.find({ type: 'Markdown' }))?.text).toContain('file:///r/png/a-p2.png')
  expect(reads.at(-1)).toBe('/r/png/a-p2.png')
  await ui.unmount()
})
