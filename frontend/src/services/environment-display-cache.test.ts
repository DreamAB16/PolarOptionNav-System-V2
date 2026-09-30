import { describe, expect, it } from 'vitest'
import { EnvironmentDisplayCache, environmentSampleSpacing, normalizeDisplayTime } from './environment-display-cache'

describe('EnvironmentDisplayCache', () => {
  it('returns cached values and evicts the least recently used entry', () => {
    const cache = new EnvironmentDisplayCache<number>(2)
    cache.set('a', 1); cache.set('b', 2)
    expect(cache.get('a')).toBe(1)
    cache.set('c', 3)
    expect(cache.has('a')).toBe(true)
    expect(cache.has('b')).toBe(false)
    expect(cache.size).toBe(2)
  })

  it('shares equivalent provider times and changes LOD with zoom', () => {
    expect(normalizeDisplayTime(new Date('2025-08-15T13:00:00Z'), 3)).toBe('2025-08-15T12:00:00.000Z')
    expect(environmentSampleSpacing('wind', 2)).toBeGreaterThan(environmentSampleSpacing('wind', 9))
    expect(environmentSampleSpacing('current', 2)).toBeGreaterThan(environmentSampleSpacing('current', 9))
    expect(environmentSampleSpacing('wave', 2)).toBeGreaterThan(environmentSampleSpacing('wave', 9))
  })
})
