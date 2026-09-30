const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface EnvironmentTimeState {
  simulation_time: string
  forecast_time: string | null
  time_step_seconds: number
  scenario: EnvironmentScenario
  range_start: string
  range_end: string
  is_playing: boolean
}

export type EnvironmentScenario = 'winter' | 'summer'
export type PlaybackSpeed = 1 | 2 | 5

export const ENVIRONMENT_SCENARIOS: Readonly<Record<EnvironmentScenario, { label: string; start: string; end: string }>> = {
  winter: { label: '冬季场景', start: '2025-02-08T00:00:00Z', end: '2025-02-22T23:00:00Z' },
  summer: { label: '夏季场景', start: '2025-08-08T00:00:00Z', end: '2025-08-22T23:00:00Z' },
}

/** Dates currently available for manual environment-data inspection. */
export const AVAILABLE_ENVIRONMENT_DATES = ['2025-02-15', '2025-08-15'] as const

export function scenarioHourCount(scenario: EnvironmentScenario): number {
  const range = ENVIRONMENT_SCENARIOS[scenario]
  return Math.round((Date.parse(range.end) - Date.parse(range.start)) / 3_600_000)
}

export function scenarioHour(time: string, scenario: EnvironmentScenario): number {
  return Math.max(0, Math.min(scenarioHourCount(scenario), Math.round((Date.parse(time) - Date.parse(ENVIRONMENT_SCENARIOS[scenario].start)) / 3_600_000)))
}

export function timestampAtScenarioHour(scenario: EnvironmentScenario, hour: number): string {
  const safeHour = Math.max(0, Math.min(scenarioHourCount(scenario), Math.round(hour)))
  return new Date(Date.parse(ENVIRONMENT_SCENARIOS[scenario].start) + safeHour * 3_600_000).toISOString()
}

export function nearestAvailableIceTime(time: Date): string {
  const requested = time.getTime()
  return AVAILABLE_ENVIRONMENT_DATES
    .map((date) => environmentTimestampForDate(date))
    .reduce((best, candidate) => Math.abs(Date.parse(candidate) - requested) < Math.abs(Date.parse(best) - requested) ? candidate : best)
}

type TimeChangeHandler = (time: Date) => void | Promise<void>

/** UI-owned playback clock; providers still resolve every explicit UTC request. */
export class EnvironmentPlaybackClock {
  private currentTime: Date
  private currentScenario: EnvironmentScenario
  private currentSpeed: PlaybackSpeed = 1
  private playing = false
  private timer: ReturnType<typeof setTimeout> | undefined

  constructor(
    private readonly onChange: TimeChangeHandler,
    initialTime = new Date('2025-02-15T12:00:00Z'),
    scenario: EnvironmentScenario = 'winter',
  ) {
    this.currentScenario = scenario
    this.currentTime = this.clamp(initialTime)
  }

  get time(): Date { return new Date(this.currentTime) }
  get scenario(): EnvironmentScenario { return this.currentScenario }
  get speed(): PlaybackSpeed { return this.currentSpeed }
  get isPlaying(): boolean { return this.playing }

  async setTime(time: Date): Promise<void> {
    this.currentTime = this.clamp(time)
    await this.onChange(this.time)
  }

  async setScenario(scenario: EnvironmentScenario): Promise<void> {
    this.currentScenario = scenario
    await this.setTime(new Date(ENVIRONMENT_SCENARIOS[scenario].start))
  }

  async next(): Promise<void> { await this.step(1) }
  async previous(): Promise<void> { await this.step(-1) }

  setSpeed(speed: PlaybackSpeed): void {
    this.currentSpeed = speed
    if (this.playing) this.schedule()
  }

  play(): void {
    if (this.playing) return
    this.playing = true
    this.schedule()
  }

  pause(): void {
    this.playing = false
    if (this.timer !== undefined) clearTimeout(this.timer)
    this.timer = undefined
  }

  dispose(): void { this.pause() }

  private async step(direction: -1 | 1): Promise<void> {
    const before = this.currentTime.getTime()
    this.currentTime = this.clamp(new Date(before + direction * 3_600_000))
    if (this.currentTime.getTime() === before && direction > 0) this.pause()
    await this.onChange(this.time)
  }

  private schedule(): void {
    if (this.timer !== undefined) clearTimeout(this.timer)
    if (!this.playing) return
    this.timer = setTimeout(() => void this.tick(), 1200 / this.currentSpeed)
  }

  private async tick(): Promise<void> {
    this.timer = undefined
    await this.step(1)
    if (this.playing) this.schedule()
  }

  private clamp(time: Date): Date {
    const range = ENVIRONMENT_SCENARIOS[this.currentScenario]
    const value = time.getTime()
    if (!Number.isFinite(value)) throw new Error('环境时间无效。')
    return new Date(Math.max(Date.parse(range.start), Math.min(Date.parse(range.end), value)))
  }
}

/** Use noon UTC to avoid local-time date shifts in tile requests. */
export function environmentTimestampForDate(date: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error('环境日期格式无效。')
  const timestamp = `${date}T12:00:00Z`
  const parsed = new Date(timestamp)
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) {
    throw new Error('环境日期无效。')
  }
  return timestamp
}

/** Read the backend-owned environment clock; the UI never invents a data date. */
export async function getEnvironmentTime(signal?: AbortSignal): Promise<EnvironmentTimeState | undefined> {
  try {
    const response = await fetch(`${apiBaseUrl}/api/environment/time`, { signal })
    if (!response.ok) return undefined
    return (await response.json()) as EnvironmentTimeState
  } catch {
    return undefined
  }
}

/** Render an unambiguous UTC bridge-display timestamp. */
export function formatEnvironmentTime(timestamp: string): string {
  const time = new Date(timestamp)
  if (Number.isNaN(time.getTime())) return '不可用'
  return `${time.getUTCFullYear()}-${String(time.getUTCMonth() + 1).padStart(2, '0')}-${String(time.getUTCDate()).padStart(2, '0')} ${String(time.getUTCHours()).padStart(2, '0')}:${String(time.getUTCMinutes()).padStart(2, '0')} 协调世界时`
}
