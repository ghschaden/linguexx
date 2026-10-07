import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Shown } from '../types'

// CLAUDE.md has Claude render every PDF and LOOK at it before calling it
// right.  This pane shows the person the same picture: the last PNG that
// `lxx png` wrote, or that Claude read -- reading an image is how Claude
// looks at it, so that is the page its verdict was about.

const PANE = 'lxx-render'
const shown = atom({ plugin: 'lxx-render', key: 'shown' } as const, null)

// `lxx png` prints one line per page: "<path>.png  721x1223px  (...)".
const LXX_PNG = /(?:^|\s)(\/\S+\.png)\s+\d+x\d+px/gm

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

/** The first bytes of base64 text, decoded by hand: no atob here. */
function head(base64: string, n: number): number[] {
  const out: number[] = []
  let bits = 0
  let acc = 0
  for (const ch of base64) {
    const v = B64.indexOf(ch)
    if (v < 0) break
    acc = (acc << 6) | v
    bits += 6
    if (bits >= 8) {
      bits -= 8
      out.push((acc >> bits) & 0xff)
      if (out.length === n) break
    }
  }
  return out
}

/** Width and height from a PNG's IHDR, or undefined if it is not one. */
export function pngSize(base64: string): { width: number; height: number } | undefined {
  const b = head(base64, 24)
  const sig = [0x89, 0x50, 0x4e, 0x47]
  if (b.length < 24 || sig.some((v, i) => b[i] !== v)) return undefined
  const u32 = (i: number) => ((b[i]! << 24) | (b[i + 1]! << 16) | (b[i + 2]! << 8) | b[i + 3]!) >>> 0
  return { width: u32(16), height: u32(20) }
}

/** The cell box for a picture: as wide as there is room, as tall as the
 *  aspect ratio wants (a cell is about twice as tall as it is wide), and
 *  narrower when that would not fit the rows there are. */
export function fit(px: { width: number; height: number }, room: { columns: number; rows: number }) {
  let columns = Math.max(1, Math.min(255, room.columns))
  let rows = Math.round((columns * px.height) / px.width / 2)
  if (rows > room.rows) {
    rows = room.rows
    columns = Math.max(1, Math.round((rows * 2 * px.width) / px.height))
  }
  return { columns, rows: Math.max(1, Math.min(255, rows)) }
}

async function show($: EngineInterface, path: string, via: Shown['via']): Promise<void> {
  const at = await $.clock.now()
  await update($, shown, () => ({ path, via, at }))
  void $.ui.open({ id: PANE, title: 'Last rendering' })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'lxx-render',
      description: 'Show the last rendering Claude made or looked at',
    })
    return next(e)
  })

  on('command.run', { command: 'lxx-render' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Last rendering' })
    return { text: 'Last rendering pane opened.' }
  })

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || ran.isError === true) return ran
    if (e.tool === 'Read' && /\.png$/i.test(e.file_path)) {
      await show($, e.file_path, 'Read')
    } else if (e.tool === 'Bash' && /\blxx\b[^|;&\n]*\spng\b/.test(e.command)) {
      const paths = [...(ran.text ?? '').matchAll(LXX_PNG)].map(m => m[1]!)
      const last = paths.at(-1)
      if (last !== undefined) await show($, last, 'lxx png')
    }
    return ran
  }).catch(($, e, next) => next(e)) // a picture never blocks a tool

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Image, Markdown } = $.ui.resolve(e)
    const now = await read($, shown)
    if (now === null) {
      return (
        <Box flexDirection="column">
          <Text dimColor>No rendering yet. One appears here when Claude runs</Text>
          <Text dimColor>`lxx png` or reads a .png.</Text>
        </Box>
      )
    }
    const name = now.path.split('/').at(-1) ?? now.path
    const link = <Markdown text={`[${name}](file://${now.path}) — via ${now.via}`} />
    let bytes: string
    try {
      bytes = (await $.fs.read(now.path, { as: 'bytes' })).base64
    } catch {
      return (
        <Box flexDirection="column">
          <Text dimColor>{now.path} is gone (a later build replaced it?).</Text>
        </Box>
      )
    }
    const px = pngSize(bytes)
    const room = {
      columns: Math.max(10, (e.viewport?.columns ?? 80) - 2),
      rows: Math.max(4, (e.viewport?.rows ?? 30) - 4),
    }
    const box = px ? fit(px, room) : { columns: room.columns, rows: room.rows }
    return (
      <Box flexDirection="column">
        <Image source={{ png: bytes }} columns={box.columns} rows={box.rows}
               alt={`${name}: this terminal cannot draw images; open the link below`} />
        {link}
      </Box>
    )
  })
}
