export type Shown = {
  /** Absolute path of the PNG. */
  path: string
  /** What put it there: `lxx png` or a Read of the image. */
  via: 'lxx png' | 'Read'
  /** When, ms since the epoch. */
  at: number
}

declare module 'claude-code' {
  interface PluginState {
    'lxx-render': { shown: Shown | null }
  }
}
