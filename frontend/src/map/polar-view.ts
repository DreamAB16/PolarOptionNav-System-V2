import Map from 'ol/Map'
import View from 'ol/View'
import { fromLonLat, get as getProjection, transform } from 'ol/proj'
import { register } from 'ol/proj/proj4'
import proj4 from 'proj4'

export type MapViewMode = 'standard' | 'polar'
export type PolarNavigationLevel = 'strategic' | 'tactical'

export const POLAR_PROJECTION_CODE = 'EPSG:3413'
export const STANDARD_PROJECTION_CODE = 'EPSG:3857'
/**
 * The navigable strategic domain, reaching approximately 30°N on its cardinal
 * axes.  This bounds the polar View only; it must not define a raster source's
 * reprojection tile matrix.
 */
export const POLAR_STRATEGIC_VIEW_EXTENT = [-7_150_000, -7_150_000, 7_150_000, 7_150_000]
/**
 * Existing native environmental grids retain this extent.  In particular, it
 * is no longer installed on the EPSG:3413 Projection and is never used by OSM.
 */
export const POLAR_VIEW_EXTENT = POLAR_STRATEGIC_VIEW_EXTENT
/** Existing native ice-tile matrix remains bounded by its published Arctic coverage. */
export const POLAR_ICE_TILE_EXTENT = [-3_314_693, -3_314_693, 3_314_693, 3_314_693]

export const POLAR_LEVEL_ZOOMS: Readonly<Record<PolarNavigationLevel, number>> = {
  strategic: 1.5,
  tactical: 9,
}

proj4.defs(
  POLAR_PROJECTION_CODE,
  '+proj=stere +lat_0=90 +lat_ts=70 +lon_0=-45 +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs +type=crs',
)
register(proj4)

const polarProjection = getProjection(POLAR_PROJECTION_CODE)!
if (!polarProjection) throw new Error('无法注册北极极射投影。')

export function createStandardView(): View {
  return new View({
    projection: STANDARD_PROJECTION_CODE,
    center: fromLonLat([18.96, 69.65]),
    zoom: 5,
  })
}

export function createPolarView(): View {
  return new View({
    projection: polarProjection,
    center: [0, 0],
    zoom: POLAR_LEVEL_ZOOMS.strategic,
    minZoom: 0,
    extent: POLAR_STRATEGIC_VIEW_EXTENT,
    showFullExtent: true,
  })
}

/** Switch views without fitting to any chart or environmental layer extent. */
export function setMapViewMode(map: Map, mode: MapViewMode): void {
  const view = mode === 'polar' ? createPolarView() : createStandardView()
  map.setView(view)
}

/** Apply stable strategic and detailed polar-view presets. */
export function setPolarNavigationLevel(map: Map, level: PolarNavigationLevel): void {
  const view = map.getView()
  if (view.getProjection().getCode() !== POLAR_PROJECTION_CODE) return

  const centerLonLat: [number, number] = level === 'strategic'
    ? [-45, 90]
    : [18.96, 69.65]
  view.setCenter(transform(centerLonLat, 'EPSG:4326', POLAR_PROJECTION_CODE))
  view.setZoom(POLAR_LEVEL_ZOOMS[level])
}

/** Backward-compatible command used by existing callers. */
export function focusPolarView(map: Map): void {
  setMapViewMode(map, 'polar')
}
