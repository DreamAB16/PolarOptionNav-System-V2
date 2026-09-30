import { describe, expect, it } from 'vitest'
import { LAYER_LABELS, LAYER_STATE_LABELS } from './ui-labels'

describe('中文驾驶台标签', () => {
  it('maps every map layer and lifecycle state to Chinese', () => {
    expect(LAYER_LABELS.ice).toBe('海冰')
    expect(LAYER_LABELS.bathymetry).toBe('水深')
    expect(LAYER_STATE_LABELS.loading).toBe('加载中')
    expect(LAYER_STATE_LABELS.ready).toBe('正常')
  })
})
