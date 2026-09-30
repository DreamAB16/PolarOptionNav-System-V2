import { describe, expect, it } from 'vitest'
import { createCoastlineLayer } from './chart-client'

describe('createCoastlineLayer', () => {
  it('converts server GeoJSON into an OpenLayers vector layer', () => {
    const layer = createCoastlineLayer({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { featurecla: 'Coastline' },
          geometry: { type: 'LineString', coordinates: [[18, 69], [19, 70]] },
        },
      ],
    })

    expect(layer.getSource()?.getFeatures()).toHaveLength(1)
  })
})
