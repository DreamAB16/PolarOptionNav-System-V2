import { afterEach, describe, expect, it, vi } from 'vitest'
import { EnvironmentPlaybackClock, environmentTimestampForDate, formatEnvironmentTime, getEnvironmentTime, scenarioHourCount, timestampAtScenarioHour } from './environment-time'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('environment time status', () => {
  it('loads the backend simulation clock', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        simulation_time: '2025-02-15T12:00:00Z', forecast_time: '2025-02-15T12:00:00Z', time_step_seconds: 3600,
      }),
    }))

    expect(await getEnvironmentTime()).toMatchObject({ simulation_time: '2025-02-15T12:00:00Z', time_step_seconds: 3600 })
  })

  it('formats a stable UTC bridge-display value', () => {
    expect(formatEnvironmentTime('2025-02-15T12:00:00Z')).toBe('2025-02-15 12:00 协调世界时')
    expect(environmentTimestampForDate('2025-08-15')).toBe('2025-08-15T12:00:00Z')
  })

  it('switches scenarios and steps over the full hourly range', async () => {
    const changed: string[] = []
    const clock = new EnvironmentPlaybackClock((time) => { changed.push(time.toISOString()) })
    await clock.setScenario('summer')
    await clock.next()
    expect(changed).toEqual(['2025-08-08T00:00:00.000Z', '2025-08-08T01:00:00.000Z'])
    expect(scenarioHourCount('summer')).toBe(359)
    expect(timestampAtScenarioHour('summer', 359)).toBe('2025-08-22T23:00:00.000Z')
  })

  it('plays, pauses and waits for the active refresh before another tick', async () => {
    vi.useFakeTimers()
    let finishRefresh: (() => void) | undefined
    const changes = vi.fn(() => new Promise<void>((resolve) => { finishRefresh = resolve }))
    const clock = new EnvironmentPlaybackClock(changes)
    clock.play()
    await vi.advanceTimersByTimeAsync(1200)
    expect(changes).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(changes).toHaveBeenCalledTimes(1)
    finishRefresh?.()
    await Promise.resolve()
    clock.pause()
    await vi.advanceTimersByTimeAsync(5000)
    expect(changes).toHaveBeenCalledTimes(1)
  })

  it('advances twenty rapid manual steps without applying an older time', async () => {
    const applied: string[] = []
    const clock = new EnvironmentPlaybackClock(async (time) => { applied.push(time.toISOString()) })
    for (let index = 0; index < 20; index += 1) await clock.next()
    expect(applied).toHaveLength(20)
    expect(applied.at(-1)).toBe('2025-02-16T08:00:00.000Z')
  })
})
