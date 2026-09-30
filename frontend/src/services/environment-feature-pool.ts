import Feature from 'ol/Feature'
import VectorSource from 'ol/source/Vector'

/** Reuses OpenLayers Feature objects and hides unused pool entries. */
export class EnvironmentFeaturePool<T> {
  readonly source = new VectorSource()
  private readonly features: Feature[] = []

  update(items: readonly T[], apply: (feature: Feature, item: T) => boolean): number {
    let active = 0
    items.forEach((item, index) => {
      const feature = this.features[index] ?? this.createFeature()
      if (apply(feature, item)) active += 1
      else feature.setGeometry(undefined)
    })
    for (let index = items.length; index < this.features.length; index += 1) {
      this.features[index].setGeometry(undefined)
    }
    this.source.changed()
    return active
  }

  get size(): number { return this.features.length }
  get activeCount(): number { return this.features.filter((feature) => feature.getGeometry() !== undefined).length }

  clear(): void {
    this.source.clear(true)
    this.features.length = 0
  }

  private createFeature(): Feature {
    const feature = new Feature()
    this.features.push(feature)
    this.source.addFeature(feature)
    return feature
  }
}
