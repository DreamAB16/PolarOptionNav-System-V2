import type OlMap from 'ol/Map'

export type DynamicEnvironmentLayer = 'wind' | 'current' | 'wave'

/** Small generic LRU used for already sampled viewport responses. */
export class EnvironmentDisplayCache<T> {
  private readonly entries = new globalThis.Map<string, T>()

  constructor(readonly maximumEntries = 10) {
    if (maximumEntries < 1) throw new Error('Display cache size must be positive.')
  }

  get(key: string): T | undefined {
    const value = this.entries.get(key)
    if (value === undefined) return undefined
    this.entries.delete(key)
    this.entries.set(key, value)
    return value
  }

  set(key: string, value: T): void {
    this.entries.delete(key)
    this.entries.set(key, value)
    while (this.entries.size > this.maximumEntries) {
      const oldest = this.entries.keys().next().value as string | undefined
      if (oldest === undefined) break
      this.entries.delete(oldest)
    }
  }

  has(key: string): boolean { return this.entries.has(key) }
  clear(): void { this.entries.clear() }
  get size(): number { return this.entries.size }
}

/** Runs bounded speculative requests sequentially and cancels them on interaction. */
export class EnvironmentPrefetchQueue {
  private controller?: AbortController
  private timer?: ReturnType<typeof setTimeout>

  schedule(tasks: Array<(signal: AbortSignal) => Promise<void>>): void {
    this.cancel()
    const controller = new AbortController()
    this.controller = controller
    this.timer = setTimeout(async () => {
      for (const task of tasks) {
        if (controller.signal.aborted) return
        try { await task(controller.signal) } catch { if (!controller.signal.aborted) return }
      }
    }, 150)
  }

  cancel(): void {
    this.controller?.abort()
    this.controller = undefined
    if (this.timer !== undefined) clearTimeout(this.timer)
    this.timer = undefined
  }
}

/** Use the source cadence in cache keys so equivalent requests share display data. */
export function normalizeDisplayTime(time: Date, cadenceHours: number): string {
  const interval = cadenceHours * 3_600_000
  const quotient = time.getTime() / interval
  const lower = Math.floor(quotient)
  const index = quotient - lower <= 0.5 ? lower : lower + 1
  return new Date(index * interval).toISOString()
}

export function environmentDisplayCacheKey(
  layer: DynamicEnvironmentLayer,
  map: OlMap,
  time: Date,
  spacing: number,
  cadenceHours: number,
): string {
  const view = map.getView()
  const projection = view.getProjection().getCode()
  const resolution = view.getResolution() ?? 1
  const center = view.getCenter() ?? [0, 0]
  const size = map.getSize() ?? [1000, 700]
  // Quantize the centre by half a sample cell: tiny pans reuse the same field.
  const quantum = Math.max(1, resolution * spacing * 0.5)
  const viewport = [
    Math.round(center[0] / quantum),
    Math.round(center[1] / quantum),
    Math.round(resolution * 1e6) / 1e6,
    size[0],
    size[1],
    spacing,
  ].join(':')
  return `${layer}|${normalizeDisplayTime(time, cadenceHours)}|${projection}|${viewport}`
}

/** Pixel spacing naturally converts to a smaller geographic interval at high zoom. */
export function environmentSampleSpacing(layer: DynamicEnvironmentLayer, zoom = 3): number {
  const strategic = { wind: 165, current: 170, wave: 180 }[layer]
  const regional = { wind: 120, current: 125, wave: 135 }[layer]
  const tactical = { wind: 80, current: 85, wave: 90 }[layer]
  return zoom <= 3 ? strategic : zoom <= 7 ? regional : tactical
}
