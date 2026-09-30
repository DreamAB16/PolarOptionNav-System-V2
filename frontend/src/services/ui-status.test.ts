import { describe, expect, it } from 'vitest'
import { uiStateLabel } from './ui-status'

describe('UI data state semantics', () => {
  it.each([
    ['NOT_CONNECTED', '未接入 · NOT_CONNECTED'],
    ['NOT_CALCULATED', '未计算 · NOT_CALCULATED'],
    ['UNKNOWN', '未知 · UNKNOWN'],
    ['UNAVAILABLE', '不可用 · UNAVAILABLE'],
  ] as const)('keeps %s distinct from a numeric empty value', (state, label) => {
    expect(uiStateLabel(state)).toBe(label)
  })
})
