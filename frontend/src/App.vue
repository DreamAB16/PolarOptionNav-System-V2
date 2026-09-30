<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Feature, { type FeatureLike } from 'ol/Feature'
import Map from 'ol/Map'
import Overlay from 'ol/Overlay'
import Point from 'ol/geom/Point'
import LineString from 'ol/geom/LineString'
import Polygon from 'ol/geom/Polygon'
import Modify from 'ol/interaction/Modify'
import VectorLayer from 'ol/layer/Vector'
import { transform } from 'ol/proj'
import { getDistance } from 'ol/sphere'
import VectorSource from 'ol/source/Vector'
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from 'ol/style'
import ContextPanel from './components/ContextPanel.vue'
import EnvironmentPanel from './components/EnvironmentPanel.vue'
import EnvironmentTimeline from './components/EnvironmentTimeline.vue'
import EventPanel from './components/EventPanel.vue'
import MainNavigation from './components/MainNavigation.vue'
import MapToolbar from './components/MapToolbar.vue'
import MonitoringPanel from './components/MonitoringPanel.vue'
import PlanningPanel from './components/PlanningPanel.vue'
import TaskPanel from './components/TaskPanel.vue'
import TopStatusBar from './components/TopStatusBar.vue'
import VesselPanel from './components/VesselPanel.vue'
import { BathymetryLayer } from './map/layers/bathymetry-layer'
import { ChartLayer } from './map/layers/chart-layer'
import { CurrentLayer } from './map/layers/current-layer'
import { IceLayer } from './map/layers/ice-layer'
import { WaveLayer } from './map/layers/wave-layer'
import { WindLayer } from './map/layers/wind-layer'
import { createStandardView, setMapViewMode, setPolarNavigationLevel, type MapViewMode, type PolarNavigationLevel } from './map/polar-view'
import { EnvironmentPlaybackClock, formatEnvironmentTime, getEnvironmentTime, type EnvironmentScenario, type PlaybackSpeed } from './services/environment-time'
import { getEnvironmentProviderStatuses, type EnvironmentLayerKey, type EnvironmentProviderStatus } from './services/environment-layer-info'
import { DEFAULT_ICE_OPACITY, ICE_LEGENDS, type IceDisplayMode } from './services/ice-layer'
import { MapLayerManager, type LayerKey, type LayerState } from './services/map-layer-manager'
import { getCurrentVessel, getNorthernEnvironmentGrid, inspectEnvironmentGridCell, isSystemOnline, planRoute } from './services/system-client'
import { WAVE_HEIGHT_LEGEND } from './services/wave-field'
import type { GeoPoint, NavigationTask, PickTarget, PlannerRiskLayers, PlannerRoute, PlanningStatus, PrimaryPanel, TaskDraft, VesselProfileResponse, VesselSummary } from './types/bridge'
import type { CaptainDraftRoute, DraftWaypoint } from './types/navigation'
import { addWaypoint, createCaptainDraft, deleteWaypoint, toggleWaypointFlag, updateWaypoint } from './services/route-draft'

const mapElement = ref<HTMLElement | null>(null)
const mapStage = ref<HTMLElement | null>(null)
const wavePopupElement = ref<HTMLElement | null>(null)
const apiStatus = ref('正在连接…')
const apiOnline = ref(false)
const activePanel = ref<PrimaryPanel>('environment')
const rightPanelOpen = ref(true)
const activeTool = ref<string>()
const toast = ref<string>()
const task = ref<NavigationTask>()
const selectedVessel = ref<VesselSummary>()
const pickedStart = ref<GeoPoint>()
const pickedDestination = ref<GeoPoint>()
const pickTarget = ref<PickTarget>()
const currentCoordinate = ref<string>()
const measurePoints: Array<[number, number]> = []
const routes = ref<PlannerRoute[]>([])
type RiskLayerName = 'rio' | 'fog' | 'wind' | 'wave' | 'depth' | 'combined'
const riskLayerNames: RiskLayerName[] = ['rio', 'fog', 'wind', 'wave', 'depth', 'combined']
const riskLayerLabels: Record<RiskLayerName, string> = { rio: '海冰 RIO', fog: '雾风险', wind: '风风险', wave: '浪风险', depth: '水深风险', combined: '综合风险' }
const northeastPassageRegion = { south: 60, north: 80, planningWest: 30, planningEast: 191.023056 }
const MAX_VIEWPORT_GRID_CELLS = 1600
const riskLayerVisibility = ref<Record<RiskLayerName, boolean>>({ rio: false, fog: false, wind: false, wave: false, depth: false, combined: false })
const riskLayersData = ref<PlannerRiskLayers>()
const northernGridVisible = ref(false)
const northernGridLoading = ref(false)
const northernGridData = ref<PlannerRiskLayers>()
const selectedEnvironmentCell = ref<Record<string, unknown>>()
const selectedCellView = computed(() => {
  const cell = selectedEnvironmentCell.value
  if (!cell) return undefined
  const environment = (cell.environment ?? {}) as Record<string, unknown>
  const risk = (cell.risk ?? {}) as Record<string, unknown>
  return {
    id: String(cell.cell_id ?? 'environment-cell'),
    isLand: Boolean(cell.is_land),
    obstacleType: cell.obstacle_type ? String(cell.obstacle_type) : undefined,
    lat: Number((cell.center as { latitude?: number } | undefined)?.latitude ?? 0),
    lon: Number((cell.center as { longitude?: number } | undefined)?.longitude ?? 0),
    depth: environment.depth_m,
    ice: risk.rio,
    fog: risk.fog,
    wind: risk.wind,
    wave: risk.wave,
    depthRisk: risk.depth,
    combined: risk.combined,
    speed: cell.effective_speed_kn,
    traversable: Boolean(cell.traversable),
    quality: cell.quality as Record<string, string> | undefined,
  }
})
const plannerStatus = ref<PlanningStatus>('not_started')
const plannerError = ref<string>()
const selectedRouteIndex = ref<number>()
const recommendedRouteIndex = ref<number>()
const captainDraft = ref<CaptainDraftRoute>()
const selectedWaypointId = ref<string>()
const routeEditMode = ref(false)
const undoStack = ref<CaptainDraftRoute[]>([])
const redoStack = ref<CaptainDraftRoute[]>([])
const sampleVessel: VesselSummary = { id: 'xuelong2', name: '雪龙2号', type: '极地科学考察破冰船', iceClass: 'PC3', length: 122.5, beam: 22.32, draft: 7.85, maxSpeed: 18, propulsion: '柴油电力推进，2×7.5 MW Azipod', propulsionPowerMw: 15, iceThickness: 1.5, snowThickness: 0.2, iceSpeed: '2–3 kn', enduranceNmi: 20000, enduranceDays: 60 }

const iceOpacity = ref(DEFAULT_ICE_OPACITY)
const iceMode = ref<IceDisplayMode>('concentration')
const mapViewMode = ref<MapViewMode>('standard')
const polarNavigationLevel = ref<PolarNavigationLevel>('strategic')
const simulationTime = ref('2025-02-15T12:00:00Z')
const environmentScenario = ref<EnvironmentScenario>('winter')
const playbackSpeed = ref<PlaybackSpeed>(1)
const timelinePlaying = ref(false)
const timelineLoading = ref(false)
const simulationTimeLabel = computed(() => formatEnvironmentTime(simulationTime.value))
const topTimeLabel = computed(() => simulationTimeLabel.value.replace(' 协调世界时', ' UTC'))
const iceLegend = computed(() => ICE_LEGENDS[iceMode.value])
const iceLegendTitle = computed(() => iceMode.value === 'concentration' ? '海冰密集度' : '海冰厚度')
const selectedWave = ref<{ matched_time: string; wave_height: number; wave_period: number; wave_direction_from: number }>()
const layers = ref<Record<LayerKey, boolean>>({ charts: true, bathymetry: true, ice: false, wind: false, current: false, wave: false, route: false, vessel: false })
const layerStates = ref<Record<LayerKey, LayerState>>({ charts: 'idle', bathymetry: 'idle', ice: 'idle', wind: 'idle', current: 'idle', wave: 'idle', route: 'idle', vessel: 'idle' })
const layerErrors = ref<Partial<Record<LayerKey, string>>>({})
const providerStatuses = ref<Partial<Record<EnvironmentLayerKey, EnvironmentProviderStatus>>>({})
const matchedTimes = ref<Partial<Record<EnvironmentLayerKey, string>>>({})
const environmentKeys: LayerKey[] = ['charts', 'bathymetry', 'ice', 'wind', 'current', 'wave']
const registeredLayers = new Set<LayerKey>(environmentKeys)
const unsubscribeState: Array<() => void> = []
let toastTimer: number | undefined
let gridRefreshTimer: number | undefined
let gridRequestId = 0
let gridAbortController: AbortController | undefined
let layerManager: MapLayerManager | undefined
let olMap: Map | undefined
let selectionLayer: VectorLayer<VectorSource> | undefined
let selectionSource: VectorSource | undefined
let draftLayer: VectorLayer<VectorSource> | undefined
let draftSource: VectorSource | undefined
let routeLayer: VectorLayer<VectorSource> | undefined
let routeSource: VectorSource | undefined
const riskSources = new globalThis.Map<RiskLayerName, VectorSource>()
const riskLayers = new globalThis.Map<RiskLayerName, VectorLayer<VectorSource>>()
let draftModify: Modify | undefined
let iceLayer: IceLayer | undefined
let chartLayer: ChartLayer | undefined
let bathymetryLayer: BathymetryLayer | undefined
let windLayer: WindLayer | undefined
let currentLayer: CurrentLayer | undefined
let waveLayer: WaveLayer | undefined
let wavePopupOverlay: Overlay | undefined
let environmentClock: EnvironmentPlaybackClock | undefined
let timeUpdateId = 0

onMounted(async () => {
  const manager = new MapLayerManager()
  layerManager = manager
  selectionSource = new VectorSource()
  selectionLayer = new VectorLayer({ source: selectionSource, style: markerStyle })
  selectionLayer.setZIndex(100)
  draftSource = new VectorSource()
  draftLayer = new VectorLayer({ source: draftSource, style: draftStyle })
  draftLayer.setZIndex(90)
  draftLayer.set('managedLayerId', 'captain-draft')
  routeSource = new VectorSource()
  routeLayer = new VectorLayer({ source: routeSource, style: plannerRouteStyle })
  routeLayer.setZIndex(80)
  routeLayer.set('managedLayerId', 'planner-route')
  const riskOlLayers = riskLayerNames.map((name, index) => {
    const source = new VectorSource()
    const layer = new VectorLayer({ source, style: (feature) => riskCellStyle(feature) })
    layer.setZIndex(20 + index)
    layer.set('managedLayerId', `risk-${name}`)
    riskSources.set(name, source); riskLayers.set(name, layer)
    return layer
  })
  // Local marine-chart mode: the map canvas supplies a plain ocean background;
  // coastline and bathymetry are served by our own backend layers. This keeps
  // road labels and external OSM tile requests out of the navigation view.
  olMap = new Map({ target: mapElement.value ?? undefined, layers: [...riskOlLayers, routeLayer, draftLayer, selectionLayer], view: createStandardView() })
  manager.attach(olMap)
  wavePopupOverlay = new Overlay({ element: wavePopupElement.value ?? undefined, offset: [10, -10], positioning: 'bottom-left', stopEvent: true })
  olMap.addOverlay(wavePopupOverlay)
  chartLayer = new ChartLayer(); manager.register(chartLayer)
  bathymetryLayer = new BathymetryLayer(); manager.register(bathymetryLayer)
  iceLayer = new IceLayer(); manager.register(iceLayer)
  windLayer = new WindLayer(); manager.register(windLayer)
  currentLayer = new CurrentLayer(); manager.register(currentLayer)
  waveLayer = new WaveLayer(); manager.register(waveLayer)
  registeredLayers.forEach((key) => unsubscribeState.push(manager.subscribe(key, (state, error) => { layerStates.value[key] = state; layerErrors.value[key] = error?.message })))
  const [online, timeState, statuses, vesselProfile] = await Promise.all([
    isSystemOnline(),
    getEnvironmentTime(),
    getEnvironmentProviderStatuses(),
    getCurrentVessel(),
  ])
  if (vesselProfile) selectedVessel.value = profileToSummary(vesselProfile)
  apiOnline.value = online
  apiStatus.value = online ? '正常' : '不可用'
  providerStatuses.value = statuses
  if (timeState) {
    simulationTime.value = timeState.simulation_time
    environmentScenario.value = timeState.scenario
    await manager.updateTime(new Date(timeState.simulation_time))
  }
  environmentClock = new EnvironmentPlaybackClock(async (time) => {
    await applyEnvironmentTime(time)
    syncClockState()
  }, new Date(simulationTime.value), environmentScenario.value)
  await Promise.all(environmentKeys.filter((key) => layers.value[key]).map(applyVisibility))
  olMap.on('moveend', refreshViewportLayers)
  olMap.on('singleclick', handleMapClick)
})

function markerStyle(feature: FeatureLike): Style {
  const kind = feature.get('kind') as string
  const color = kind === 'start' ? '#62d6b5' : kind === 'destination' ? '#f0b862' : '#7ec8e3'
  const label = kind === 'start' ? '起' : kind === 'destination' ? '终' : '点'
  return new Style({ image: new CircleStyle({ radius: 8, fill: new Fill({ color }), stroke: new Stroke({ color: '#06131d', width: 3 }) }), text: new Text({ text: label, offsetY: -19, fill: new Fill({ color: '#fff' }), stroke: new Stroke({ color: '#06131d', width: 3 }), font: '600 12px sans-serif' }) })
}

function draftStyle(feature: FeatureLike): Style {
  const kind = feature.get('draftKind') as string
  if (kind === 'route') return new Style({ stroke: new Stroke({ color: '#e7c56d', width: 3, lineDash: [8, 5] }) })
  const selected = feature.get('waypointId') === selectedWaypointId.value
  return new Style({ image: new CircleStyle({ radius: selected ? 8 : 6, fill: new Fill({ color: selected ? '#f6d883' : '#e7c56d' }), stroke: new Stroke({ color: '#071822', width: 2 }) }), text: new Text({ text: String(feature.get('sequence') ?? ''), offsetY: -16, fill: new Fill({ color: '#fff' }), stroke: new Stroke({ color: '#071822', width: 3 }), font: '600 11px sans-serif' }) })
}

function plannerRouteStyle(feature: FeatureLike): Style {
  const selected = feature.get('routeIndex') === selectedRouteIndex.value
  const recommended = feature.get('routeRole') === 'recommended'
  return new Style({
    stroke: new Stroke({
      color: selected ? '#f6d883' : recommended ? '#62d6b5' : '#6d9fc4',
      width: selected ? 5 : recommended ? 4 : 2.5,
      lineDash: recommended ? undefined : [10, 7],
    }),
  })
}

function riskCellStyle(feature: FeatureLike): Style {
  const cell = feature.get('cellData') as { is_land?: boolean; traversable?: boolean } | undefined
  if (cell?.is_land || cell?.traversable === false) {
    return new Style({ fill: new Fill({ color: 'rgba(30, 40, 45, 0.76)' }), stroke: new Stroke({ color: 'rgba(120, 130, 135, 0.88)', width: 1.2 }) })
  }
  const value = Number(feature.get('riskValue') ?? 0)
  const color = value >= 0.75 ? '#ef4444' : value >= 0.5 ? '#f4df22' : value >= 0.25 ? '#78d84f' : '#53a7df'
  return new Style({ fill: new Fill({ color: `${color}cc` }), stroke: new Stroke({ color: '#3987c4', width: 1.2 }) })
}

function renderRiskLayers(): void {
  if (!olMap) return
  const data = northernGridVisible.value ? northernGridData.value : riskLayersData.value
  if (!data) return
  const projection = olMap.getView().getProjection()
  const cells = data.cells ?? []
  if (cells.length) {
    riskLayerNames.forEach((name) => {
      const source = riskSources.get(name)
      if (!source) return
      source.clear()
      if (!riskLayerVisibility.value[name]) {
        riskLayers.get(name)?.setVisible(false)
        return
      }
      for (const cell of cells) {
        const geometry = cell.geometry
        const bounds = cell.bounds
        if (!geometry?.length && !bounds) continue
        const value = Number(cell.risk[name] ?? 0)
        const geographicCorners = geometry?.length
          ? [...geometry, geometry[0]]
          : [[bounds!.west, bounds!.south], [bounds!.east, bounds!.south], [bounds!.east, bounds!.north], [bounds!.west, bounds!.north], [bounds!.west, bounds!.south]]
        const corners = geographicCorners.map((point) => transform(point, 'EPSG:4326', projection))
        source.addFeature(new Feature({ geometry: new Polygon([corners]), riskValue: Math.max(0, Math.min(1, value)), riskLayer: name, cellData: cell }))
      }
      riskLayers.get(name)?.setVisible(riskLayerVisibility.value[name])
    })
    return
  }
  if (data.width < 2 || data.height < 2 || !Array.isArray(data.latitudes) || !Array.isArray(data.longitudes) || data.latitudes.length < data.height || data.longitudes.length < data.width) return
  riskLayerNames.forEach((name) => {
    const source = riskSources.get(name)
    if (!source) return
    source.clear()
    const matrix = data.layers[name]
    for (let y = 0; y < data.height; y += 1) {
      for (let x = 0; x < data.width; x += 1) {
        const value = Number(matrix[y]?.[x] ?? 0)
        const lat = (data.latitudes as number[])[y]
        const lon = (data.longitudes as number[])[x]
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue
        const latStep = y === 0 ? Math.abs((data.latitudes as number[])[1] - lat) : y === data.height - 1 ? Math.abs(lat - (data.latitudes as number[])[y - 1]) : Math.abs((data.latitudes as number[])[y + 1] - (data.latitudes as number[])[y - 1]) / 2
        const lonStep = x === 0 ? Math.abs((data.longitudes as number[])[1] - lon) : x === data.width - 1 ? Math.abs(lon - (data.longitudes as number[])[x - 1]) : Math.abs((data.longitudes as number[])[x + 1] - (data.longitudes as number[])[x - 1]) / 2
        const corners = [[lon - lonStep / 2, lat - latStep / 2], [lon + lonStep / 2, lat - latStep / 2], [lon + lonStep / 2, lat + latStep / 2], [lon - lonStep / 2, lat + latStep / 2], [lon - lonStep / 2, lat - latStep / 2]].map((point) => transform(point, 'EPSG:4326', projection))
        source.addFeature(new Feature({ geometry: new Polygon([corners]), riskValue: Math.max(0, Math.min(1, value)), riskLayer: name }))
      }
    }
    riskLayers.get(name)?.setVisible(riskLayerVisibility.value[name])
  })
}

function toggleRiskLayer(name: RiskLayerName): void {
  riskLayerVisibility.value[name] = !riskLayerVisibility.value[name]
  renderRiskLayers()
}

function toPlanningLongitude(longitude: number): number { return longitude < 0 ? longitude + 360 : longitude }
function toDisplayLongitude(planningLongitude: number): number { return planningLongitude > 180 ? planningLongitude - 360 : planningLongitude }
function formatLongitude(longitude: number, precision = 4): string { return `${Math.abs(longitude).toFixed(precision)}°${longitude < 0 ? 'W' : 'E'}` }

function currentNorthernGridBounds(): { south: number; north: number; west: number; east: number } {
  const extent = olMap?.getView().calculateExtent(olMap.getSize())
  const projection = olMap?.getView().getProjection()
  if (!extent || !projection) return { south: 0, north: 90, west: -180, east: 180 }
  const corners = [
    transform([extent[0], extent[1]], projection, 'EPSG:4326'),
    transform([extent[0], extent[3]], projection, 'EPSG:4326'),
    transform([extent[2], extent[1]], projection, 'EPSG:4326'),
    transform([extent[2], extent[3]], projection, 'EPSG:4326'),
  ]
  const latitudes = corners.map((item) => item[1]).filter(Number.isFinite)
  const longitudes = corners.map((item) => item[0]).filter(Number.isFinite)
  const south = Math.max(0, Math.min(...latitudes))
  const north = Math.min(89.8, Math.max(...latitudes))
  const minimum = Math.max(-180, Math.min(...longitudes))
  const maximum = Math.min(180, Math.max(...longitudes))
  // A small visible arc straddling the date line looks like [-179, 179]
  // after min/max. Preserve it as 179E -> 179W for the backend.
  const crossesDateLine = maximum - minimum > 180
  const west = crossesDateLine ? maximum : minimum
  const east = crossesDateLine ? minimum : maximum
  return north > south ? { south, north, west, east } : { south: 0, north: 90, west: -180, east: 180 }
}

function visibleNortheastPassageBounds(): { south: number; north: number; west: number; east: number } | undefined {
  const bounds = currentNorthernGridBounds()
  let planningWest = toPlanningLongitude(bounds.west)
  let planningEast = toPlanningLongitude(bounds.east)
  if (bounds.west === -180 && bounds.east === 180) { planningWest = 0; planningEast = 360 }
  else if (bounds.west > bounds.east && planningEast < planningWest) planningEast += 360
  else if (bounds.west < 0 && bounds.east >= 0) {
    // A non-crossing viewport spanning Greenwich consists of two planning
    // intervals; it is too broad for a useful NEP 25 km raster.
    planningWest = 0; planningEast = 360
  }
  const clipped = {
    south: Math.max(bounds.south, northeastPassageRegion.south), north: Math.min(bounds.north, northeastPassageRegion.north),
    west: Math.max(planningWest, northeastPassageRegion.planningWest), east: Math.min(planningEast, northeastPassageRegion.planningEast),
  }
  return clipped.south < clipped.north && clipped.west < clipped.east
    ? { south: clipped.south, north: clipped.north, west: toDisplayLongitude(clipped.west), east: toDisplayLongitude(clipped.east) }
    : undefined
}

function estimatedVisibleGridCells(bounds: { south: number; north: number; west: number; east: number }): number {
  // Conservative client-side guard. The server remains authoritative because
  // fixed EPSG:3413 cells are not rectangular in longitude/latitude.
  const meanLatitude = (bounds.south + bounds.north) / 2
  const rows = (bounds.north - bounds.south) * 111.32 / 25
  let longitudeWidth = toPlanningLongitude(bounds.east) - toPlanningLongitude(bounds.west)
  if (longitudeWidth < 0) longitudeWidth += 360
  const cols = longitudeWidth * 111.32 * Math.max(Math.cos(meanLatitude * Math.PI / 180), 0.12) / 25
  return Math.ceil(rows * cols * 1.25)
}

async function loadNorthernGridForViewport(): Promise<void> {
  const requestId = ++gridRequestId
  gridAbortController?.abort()
  const controller = new AbortController()
  gridAbortController = controller
  northernGridLoading.value = true
  try {
    const bounds = visibleNortheastPassageBounds()
    if (!bounds) {
      northernGridData.value = undefined
      riskLayerNames.forEach((name) => riskSources.get(name)?.clear())
      renderRiskLayers()
      return
    }
    if (estimatedVisibleGridCells(bounds) > MAX_VIEWPORT_GRID_CELLS) {
      northernGridData.value = undefined
      riskLayerNames.forEach((name) => riskSources.get(name)?.clear())
      renderRiskLayers()
      showToast('当前地图范围过大，请放大后查看 25 km 环境风险栅格。')
      return
    }
    const data = await getNorthernEnvironmentGrid(plannerTimestamp(simulationTime.value), { ...bounds, maxCells: MAX_VIEWPORT_GRID_CELLS }, controller.signal)
    if (requestId !== gridRequestId) return
    northernGridData.value = data
    renderRiskLayers()
  } catch (error) {
    if (requestId === gridRequestId && !(error instanceof DOMException && error.name === 'AbortError')) showToast(error instanceof Error ? error.message : '视口栅格刷新失败')
  } finally {
    if (requestId === gridRequestId) northernGridLoading.value = false
  }
}

async function toggleNorthernGrid(): Promise<void> {
  if (northernGridVisible.value) {
    northernGridVisible.value = false
    selectedEnvironmentCell.value = undefined
    riskLayerNames.forEach((name) => { riskSources.get(name)?.clear(); riskLayers.get(name)?.setVisible(false) })
    return
  }
  northernGridLoading.value = true
  try {
    northernGridVisible.value = true
    riskLayerNames.forEach((name) => {
      riskLayerVisibility.value[name] = name === 'combined'
      riskLayers.get(name)?.setVisible(riskLayerVisibility.value[name])
    })
    await loadNorthernGridForViewport()
    showToast('东北航道 25 km 环境栅格已显示')
  } catch (error) {
    showToast(error instanceof Error ? error.message : '环境栅格加载失败')
  } finally {
    northernGridLoading.value = false
  }
}

function profileToSummary(profile: VesselProfileResponse): VesselSummary {
  return {
    id: profile.identity.id,
    name: profile.identity.name,
    type: profile.identity.vessel_type,
    iceClass: profile.ice_capability.ice_class,
    length: profile.geometry.length_m,
    beam: profile.geometry.beam_m,
    draft: profile.geometry.design_draft_m,
    maxSpeed: profile.speed.maximum_speed_kn,
    propulsion: profile.propulsion.type,
    propulsionPowerMw: profile.propulsion.total_propulsion_power_mw,
    iceThickness: profile.ice_capability.continuous_ice_thickness_m,
    snowThickness: profile.ice_capability.continuous_snow_thickness_m,
    iceSpeed: `${profile.ice_capability.continuous_ice_speed_min_kn}–${profile.ice_capability.continuous_ice_speed_max_kn} kn`,
    enduranceNmi: profile.speed.endurance_nmi,
    enduranceDays: profile.speed.endurance_days,
  }
}
function handleMapClick(event: { coordinate: number[]; pixel: number[] }): void {
  if (!olMap) return
  const lonLat = transform(event.coordinate, olMap.getView().getProjection(), 'EPSG:4326')
  const longitude = ((((lonLat[0] + 180) % 360) + 360) % 360) - 180
  const latitude = Math.max(-90, Math.min(90, lonLat[1]))
  const coordinate: GeoPoint = { name: `${latitude.toFixed(4)}°N, ${formatLongitude(longitude)}`, longitude, latitude }
  currentCoordinate.value = coordinate.name
  if (pickTarget.value) {
    const target = pickTarget.value
    if (target === 'start') pickedStart.value = coordinate; else pickedDestination.value = coordinate
    addSelectionMarker(target, event.coordinate)
    pickTarget.value = undefined; activeTool.value = undefined
    showToast(`${target === 'start' ? '起点' : '终点'}已设置：${coordinate.name}`)
    return
  }
  if (activeTool.value === 'coordinate' || activeTool.value === 'pick') {
    addSelectionMarker('point', event.coordinate); showToast(`坐标：${coordinate.name}`); activeTool.value = undefined; return
  }
  if (activeTool.value === 'measure') {
    measurePoints.push([lonLat[0], lonLat[1]]); addSelectionMarker('point', event.coordinate)
    if (measurePoints.length === 2) { showToast(`测距结果：${(getDistance(measurePoints[0], measurePoints[1]) / 1852).toFixed(1)} 海里`); measurePoints.splice(0); activeTool.value = undefined } else showToast('已设置测距起点，请选择终点')
    return
  }
  let selectedPlannerRoute = false
  olMap.forEachFeatureAtPixel(event.pixel, (feature, layer) => {
    if ((layer as { get?: (key: string) => unknown } | undefined)?.get?.('managedLayerId') !== 'planner-route') return undefined
    const routeIndex = feature.get('routeIndex') as number | undefined
    if (routeIndex !== undefined) {
      selectPlannerRoute(routeIndex)
      showToast(`已选择候选路线 ${routeIndex + 1}`)
      selectedPlannerRoute = true
    }
    return feature
  })
  if (selectedPlannerRoute) return
  let selectedDraftWaypoint = false
  olMap.forEachFeatureAtPixel(event.pixel, (feature, layer) => {
    if ((layer as { get?: (key: string) => unknown } | undefined)?.get?.('managedLayerId') !== 'captain-draft') return undefined
    const waypointId = feature.get('waypointId') as string | undefined
    if (waypointId) { selectedWaypointId.value = waypointId; renderCaptainDraft(); selectedDraftWaypoint = true; showToast('已选择 Captain Draft 航点') }
    return feature
  })
  if (selectedDraftWaypoint) return
  let selectedRiskCell = false
  olMap.forEachFeatureAtPixel(event.pixel, (feature, layer) => {
    const managedId = (layer as { get?: (key: string) => unknown } | undefined)?.get?.('managedLayerId')
    if (typeof managedId !== 'string' || !managedId.startsWith('risk-')) return undefined
    const cell = feature.get('cellData') as { cell_id?: string; environment?: Record<string, number | null>; risk?: Record<string, number>; quality?: Record<string, string>; effective_speed_kn?: number | null; traversable?: boolean; is_land?: boolean } | undefined
    if (cell) {
      const e = cell.environment ?? {}
      const r = cell.risk ?? {}
      selectedEnvironmentCell.value = cell as unknown as Record<string, unknown>
      showToast(cell.is_land ? `${cell.cell_id ?? '栅格'} · 陆地 · 不可通行` : `${cell.cell_id ?? '栅格'} · 水深 ${Number(e.depth_m ?? 0).toFixed(0)}m · RIO ${Number(r.rio ?? 0).toFixed(2)} · 综合 ${Number(r.combined ?? 0).toFixed(2)} · ${cell.traversable ? '可通航' : '障碍'} · ${cell.effective_speed_kn?.toFixed(1) ?? '--'} kn`)
      selectedRiskCell = true
    }
    return feature
  })
  if (selectedRiskCell) return
  if (northernGridVisible.value && latitude >= 0) {
    void inspectNorthernCell(latitude, longitude)
    return
  }
  selectedWave.value = undefined; wavePopupOverlay?.setPosition(undefined)
  olMap.forEachFeatureAtPixel(event.pixel, (feature, layer) => {
    if ((layer as { get?: (key: string) => unknown } | undefined)?.get?.('managedLayerId') !== 'wave') return undefined
    const p = feature.getProperties() as Record<string, unknown>
    if (typeof p.wave_height === 'number' && typeof p.wave_period === 'number' && typeof p.wave_direction_from === 'number') {
      selectedWave.value = { matched_time: typeof p.matched_time === 'string' ? p.matched_time : simulationTime.value, wave_height: p.wave_height, wave_period: p.wave_period, wave_direction_from: p.wave_direction_from }
      wavePopupOverlay?.setPosition(event.coordinate)
    }
    return feature
  })
}

async function inspectNorthernCell(latitude: number, longitude: number): Promise<void> {
  try {
    selectedEnvironmentCell.value = await inspectEnvironmentGridCell(latitude, longitude, plannerTimestamp(simulationTime.value))
  } catch (error) {
    showToast(error instanceof Error ? error.message : '栅格属性查询失败')
  }
}
function addSelectionMarker(kind: string, coordinate: number[]): void {
  if (kind === 'start' || kind === 'destination') selectionSource?.getFeatures().filter((feature) => feature.get('kind') === kind).forEach((feature) => selectionSource?.removeFeature(feature))
  selectionSource?.addFeature(new Feature({ geometry: new Point(coordinate), kind }))
}
function selectedWaypoint(): DraftWaypoint | undefined { return captainDraft.value?.waypoints.find((item) => item.id === selectedWaypointId.value) }
function saveDraftHistory(): void { if (captainDraft.value) { undoStack.value.push(structuredClone(captainDraft.value)); redoStack.value = [] } }
function renderCaptainDraft(): void {
  if (!draftSource || !olMap) return
  draftSource.clear()
  const draft = captainDraft.value
  if (!draft) return
  const points = draft.waypoints.map((item) => transform([item.longitude, item.latitude], 'EPSG:4326', olMap!.getView().getProjection()))
  draftSource.addFeature(new Feature({ geometry: new LineString(points), draftKind: 'route' }))
  draft.waypoints.forEach((item) => draftSource?.addFeature(new Feature({ geometry: new Point(transform([item.longitude, item.latitude], 'EPSG:4326', olMap!.getView().getProjection())), draftKind: 'waypoint', waypointId: item.id, sequence: item.sequence })))
}

function renderPlannerRoutes(): void {
  if (!routeSource || !olMap) return
  routeSource.clear()
  const visibleIndex = selectedRouteIndex.value ?? recommendedRouteIndex.value
  routes.value.forEach((route, index) => {
    if (visibleIndex !== undefined && index !== visibleIndex) return
    const coordinates = route.path.map((point) => transform([point.longitude, point.latitude], 'EPSG:4326', olMap!.getView().getProjection()))
    if (coordinates.length < 2) return
    routeSource?.addFeature(new Feature({
      geometry: new LineString(coordinates),
      routeIndex: index,
      routeRole: index === recommendedRouteIndex.value ? 'recommended' : 'alternative',
    }))
  })
  routeSource.changed()
}

function focusSelectedRoute(): void {
  if (!olMap || !routeSource || routeSource.getFeatures().length === 0) return
  const extent = routeSource.getExtent()
  if (!extent || !extent.every(Number.isFinite)) return
  olMap.getView().fit(extent, { padding: [90, 90, 90, 90], maxZoom: mapViewMode.value === 'polar' ? 7 : 6, duration: 450 })
}

function plannerRouteKey(route?: { path?: Array<{ latitude: number; longitude: number }> }): string {
  return route?.path?.map((point) => `${point.latitude.toFixed(5)},${point.longitude.toFixed(5)}`).join('|') ?? ''
}

function chooseRouteIndex(): number {
  if (!routes.value.length) return 0
  const mode = task.value?.planningMode ?? 'balanced'
  if (mode === 'fastest') return routes.value.reduce((best, route, index, all) => route.objectives.time_hours < all[best].objectives.time_hours ? index : best, 0)
  if (mode === 'lowest_risk') return routes.value.reduce((best, route, index, all) => route.objectives.risk < all[best].objectives.risk ? index : best, 0)
  const risks = routes.value.map((route) => route.objectives.risk)
  const distances = routes.value.map((route) => route.objectives.distance_km)
  const times = routes.value.map((route) => route.objectives.time_hours)
  const normalize = (value: number, values: number[]) => {
    const min = Math.min(...values)
    const max = Math.max(...values)
    return max - min > 1e-9 ? (value - min) / (max - min) : 0
  }
  return routes.value.reduce((best, route, index) => {
    const score = normalize(route.objectives.risk, risks) + normalize(route.objectives.distance_km, distances) + normalize(route.objectives.time_hours, times)
    const bestRoute = routes.value[best]
    const bestScore = normalize(bestRoute.objectives.risk, risks) + normalize(bestRoute.objectives.distance_km, distances) + normalize(bestRoute.objectives.time_hours, times)
    return score < bestScore ? index : best
  }, 0)
}

function plannerTimestamp(value: string): string {
  const normalized = value.length === 16 ? `${value}:00` : value
  return normalized.endsWith('Z') ? new Date(normalized).toISOString() : new Date(`${normalized}Z`).toISOString()
}

async function runPlanning(replanning = false): Promise<void> {
  const currentTask = task.value
  if (!currentTask?.start || !currentTask.destination) {
    plannerError.value = '请先设置起点和终点。'
    plannerStatus.value = 'failed'
    showToast(plannerError.value)
    return
  }
  plannerStatus.value = replanning ? 'replanning' : 'planning'
  plannerError.value = undefined
  try {
    const response = await planRoute({
      start: { lat: currentTask.start.latitude, lon: currentTask.start.longitude },
      goal: { lat: currentTask.destination.latitude, lon: currentTask.destination.longitude },
      departure_time: plannerTimestamp(currentTask.departureTime),
      grid_size: 20,
      cell_size_m: 25000,
      population_size: 36,
      generations: 20,
      seed: 42,
    })
    routes.value = response.routes.map((route, index) => ({ ...route, routeId: route.routeId || `pareto-${index + 1}` }))
    // Risk polygons always come from the bounded viewport query.  The global
    // planner matrix must never be converted to tens of thousands of browser
    // features after a route calculation.
    riskLayersData.value = undefined
    if (northernGridVisible.value) void loadNorthernGridForViewport()
    const recommendedKey = plannerRouteKey(response.metadata.recommended_route)
    const matchedRecommended = routes.value.findIndex((route) => plannerRouteKey(route) === recommendedKey)
    recommendedRouteIndex.value = matchedRecommended >= 0 ? matchedRecommended : 0
    selectedRouteIndex.value = chooseRouteIndex()
    plannerStatus.value = routes.value.length ? 'completed' : 'failed'
    if (!routes.value.length) throw new Error('后端未返回可行路线。')
    layers.value.route = true
    renderPlannerRoutes()
    focusSelectedRoute()
    showToast(`规划完成：已生成 ${routes.value.length} 条候选路线`)
  } catch (error) {
    routes.value = []
    selectedRouteIndex.value = undefined
    recommendedRouteIndex.value = undefined
    routeSource?.clear()
    riskLayerNames.forEach((name) => riskSources.get(name)?.clear())
    plannerStatus.value = 'failed'
    plannerError.value = error instanceof Error ? error.message : '规划失败，请检查后端服务和环境数据。'
    showToast(plannerError.value)
  }
}

function selectPlannerRoute(index: number): void {
  if (index < 0 || index >= routes.value.length) return
  selectedRouteIndex.value = index
  renderPlannerRoutes()
  focusSelectedRoute()
}

function createManualDraft(): void {
  if (!task.value?.start || !task.value.destination) return
  captainDraft.value = createCaptainDraft(task.value.start, task.value.destination)
  selectedWaypointId.value = captainDraft.value.waypoints[0].id
  undoStack.value = []; redoStack.value = []; renderCaptainDraft(); showToast('已创建 Captain Draft Route（仅前端草稿）')
}
function applyDraft(next: CaptainDraftRoute): void { saveDraftHistory(); captainDraft.value = next; renderCaptainDraft() }
function addDraftWaypoint(): void {
  const draft = captainDraft.value; if (!draft) return
  const anchor = selectedWaypoint() ?? draft.waypoints[draft.waypoints.length - 2]
  const next = draft.waypoints[Math.min(anchor.sequence, draft.waypoints.length - 1)]
  const point: GeoPoint = { name: '中间航点', longitude: (anchor.longitude + next.longitude) / 2, latitude: (anchor.latitude + next.latitude) / 2 }
  applyDraft(addWaypoint(draft, point, anchor.sequence)); selectedWaypointId.value = captainDraft.value?.waypoints[anchor.sequence]?.id
}
function insertDraftWaypoint(): void { addDraftWaypoint() }
function deleteDraftWaypoint(): void { if (captainDraft.value && selectedWaypointId.value) { applyDraft(deleteWaypoint(captainDraft.value, selectedWaypointId.value)); selectedWaypointId.value = captainDraft.value?.waypoints[0]?.id } }
function toggleDraftFlag(field: 'locked' | 'mustPass'): void { if (captainDraft.value && selectedWaypointId.value) applyDraft(toggleWaypointFlag(captainDraft.value, selectedWaypointId.value, field)) }
function undoDraft(): void { const previous = undoStack.value.pop(); if (!previous || !captainDraft.value) return; redoStack.value.push(structuredClone(captainDraft.value)); captainDraft.value = previous; renderCaptainDraft() }
function redoDraft(): void { const next = redoStack.value.pop(); if (!next || !captainDraft.value) return; undoStack.value.push(structuredClone(captainDraft.value)); captainDraft.value = next; renderCaptainDraft() }
function toggleDraftEdit(): void {
  routeEditMode.value = !routeEditMode.value
  if (!olMap || !draftSource) return
  if (routeEditMode.value) {
    draftModify = new Modify({ source: draftSource })
    draftModify.on('modifyend', () => {
      const draft = captainDraft.value; if (!draft || !olMap) return
      const features = draftSource?.getFeatures().filter((feature) => feature.get('draftKind') === 'waypoint') ?? []
      const byId = new globalThis.Map(features.map((feature) => [feature.get('waypointId') as string, feature]))
      const changed = draft.waypoints.reduce((result, item) => {
        const geometry = byId.get(item.id)?.getGeometry() as Point | undefined
        if (!geometry || item.locked) return result
        const [longitude, latitude] = transform(geometry.getCoordinates(), olMap!.getView().getProjection(), 'EPSG:4326')
        return updateWaypoint(result, item.id, { longitude, latitude })
      }, draft)
      applyDraft(changed); showToast('航点已移动；ValidationStatus 已重置为 UNCHECKED')
    })
    olMap.addInteraction(draftModify)
    showToast('编辑模式：可拖动未锁定航点')
  } else if (draftModify) { olMap.removeInteraction(draftModify); draftModify = undefined }
}
function onDraftFeatureAdded(event: { feature?: Feature }): void {
  const feature = event.feature
  const draft = captainDraft.value
  if (!feature || feature.get('draftKind') !== 'waypoint' || !draft || !olMap) return
  const pixel = olMap.getPixelFromCoordinate((feature.getGeometry() as Point).getCoordinates())
  if (!pixel) return
  const segment = draft.waypoints.slice(0, -1).map((from, index) => {
    const to = draft.waypoints[index + 1]
    const a = olMap!.getPixelFromCoordinate(transform([from.longitude, from.latitude], 'EPSG:4326', olMap!.getView().getProjection()))
    const b = olMap!.getPixelFromCoordinate(transform([to.longitude, to.latitude], 'EPSG:4326', olMap!.getView().getProjection()))
    if (!a || !b) return { index, distance: Infinity }
    const dx = b[0] - a[0], dy = b[1] - a[1]
    const t = Math.max(0, Math.min(1, ((pixel[0] - a[0]) * dx + (pixel[1] - a[1]) * dy) / Math.max(1, dx * dx + dy * dy)))
    return { index, distance: Math.hypot(pixel[0] - (a[0] + t * dx), pixel[1] - (a[1] + t * dy)) }
  }).sort((a, b) => a.distance - b.distance)[0]
  if (!segment || segment.distance > 14) return
  const [longitude, latitude] = transform((feature.getGeometry() as Point).getCoordinates(), olMap.getView().getProjection(), 'EPSG:4326')
  const next = addWaypoint(draft, { name: `航点 ${draft.waypoints.length - 1}`, longitude, latitude }, segment.index + 1)
  saveDraftHistory(); captainDraft.value = next; selectedWaypointId.value = next.waypoints[segment.index + 1].id; renderCaptainDraft()
}
async function refreshViewportLayers(): Promise<void> {
  await Promise.allSettled([layers.value.wind ? windLayer?.refresh() : undefined, layers.value.current ? currentLayer?.refresh() : undefined, layers.value.wave ? waveLayer?.refresh() : undefined])
  if (northernGridVisible.value) {
    window.clearTimeout(gridRefreshTimer)
    gridRefreshTimer = window.setTimeout(() => { void loadNorthernGridForViewport() }, 180)
  }
  syncMatchedTimes()
}
function showToast(message: string): void { toast.value = message; window.clearTimeout(toastTimer); toastTimer = window.setTimeout(() => { toast.value = undefined }, 3600) }
function toggleLayer(key: LayerKey): void { layers.value[key] = !layers.value[key]; if (key === 'wave' && !layers.value.wave) { selectedWave.value = undefined; wavePopupOverlay?.setPosition(undefined) }; void applyVisibility(key) }
async function applyVisibility(key: LayerKey): Promise<void> { if (!layerManager || !registeredLayers.has(key)) return; try { await layerManager.setVisibility(key, layers.value[key]); syncMatchedTimes() } catch { layers.value[key] = false } }
async function applyPreset(keys: LayerKey[]): Promise<void> { environmentKeys.forEach((key) => { layers.value[key] = keys.includes(key) }); await Promise.all(environmentKeys.map(applyVisibility)); showToast('环境显示预设已应用') }
function updateIceOpacity(value: number): void { iceOpacity.value = value; iceLayer?.setOpacity(value) }
function updateIceMode(value: IceDisplayMode): void { iceMode.value = value; iceLayer?.setMode(value) }
async function applyEnvironmentTime(time: Date): Promise<void> {
  const updateId = ++timeUpdateId
  simulationTime.value = time.toISOString()
  timelineLoading.value = true
  try { await layerManager?.updateTime(time) }
  finally { if (updateId === timeUpdateId) { timelineLoading.value = false; syncMatchedTimes() } }
}
function syncMatchedTimes(): void {
  matchedTimes.value = {
    ice: iceLayer?.getMatchedTime(),
    wind: windLayer?.getMatchedTime(),
    current: currentLayer?.getMatchedTime(),
    wave: waveLayer?.getMatchedTime(),
  }
}
function syncClockState(): void {
  if (!environmentClock) return
  environmentScenario.value = environmentClock.scenario
  playbackSpeed.value = environmentClock.speed
  timelinePlaying.value = environmentClock.isPlaying
}
async function changeEnvironmentScenario(scenario: EnvironmentScenario): Promise<void> { await environmentClock?.setScenario(scenario); syncClockState() }
async function seekEnvironmentTime(timestamp: string): Promise<void> { await environmentClock?.setTime(new Date(timestamp)); syncClockState() }
async function stepEnvironmentTime(direction: -1 | 1): Promise<void> { if (direction > 0) await environmentClock?.next(); else await environmentClock?.previous(); syncClockState() }
function toggleEnvironmentPlayback(): void { if (!environmentClock) return; if (environmentClock.isPlaying) environmentClock.pause(); else environmentClock.play(); syncClockState() }
function setEnvironmentPlaybackSpeed(speed: PlaybackSpeed): void { environmentClock?.setSpeed(speed); syncClockState() }
async function changeMapView(mode: MapViewMode, level?: PolarNavigationLevel): Promise<void> {
  if (!olMap) return
  const modeChanged = mode !== mapViewMode.value
  mapViewMode.value = mode
  if (modeChanged) { setMapViewMode(olMap, mode); iceLayer?.setPolarMode(mode === 'polar'); bathymetryLayer?.setPolarMode(mode === 'polar'); await chartLayer?.setProjection(mode === 'polar' ? 'EPSG:3413' : 'EPSG:3857'); renderPlannerRoutes(); renderRiskLayers(); renderCaptainDraft() }
  if (mode === 'polar') { polarNavigationLevel.value = level ?? 'strategic'; setPolarNavigationLevel(olMap, polarNavigationLevel.value) }
  refreshViewportLayers()
}
function resetView(): void { if (mapViewMode.value === 'standard') olMap?.setView(createStandardView()); else if (olMap) { setMapViewMode(olMap, 'polar'); setPolarNavigationLevel(olMap, polarNavigationLevel.value) } }
function locateVessel(): void { if (!olMap || !selectedVessel.value?.position) { showToast('未选择船舶或实时船位不可用'); return }; const point = selectedVessel.value.position; olMap.getView().animate({ center: transform([point.longitude, point.latitude], 'EPSG:4326', olMap.getView().getProjection()), zoom: mapViewMode.value === 'polar' ? 9 : 7, duration: 500 }); showToast('已定位到示例船位') }
function handleTool(tool: 'locate' | 'measure' | 'coordinate' | 'pick' | 'info' | 'fullscreen' | 'reset'): void {
  if (tool === 'locate') return locateVessel()
  if (tool === 'reset') return resetView()
  if (tool === 'info') { activePanel.value = 'environment'; showToast('环境图层状态已打开'); return }
  if (tool === 'fullscreen') { if (document.fullscreenElement) void document.exitFullscreen(); else void mapStage.value?.requestFullscreen(); return }
  activeTool.value = activeTool.value === tool ? undefined : tool; measurePoints.splice(0); showToast(tool === 'measure' ? '请在地图上依次选择两个点' : '请点击地图选择位置')
}
function beginTaskPick(target: 'start' | 'destination'): void { pickTarget.value = target; activeTool.value = 'pick'; showToast(`请在地图上选择${target === 'start' ? '起点' : '终点'}`) }
function createTask(draft: TaskDraft): void { task.value = { ...draft, start: draft.start ?? pickedStart.value, destination: draft.destination ?? pickedDestination.value, id: `task-${Date.now()}` }; if (draft.vesselId === sampleVessel.id) selectedVessel.value = sampleVessel; showToast('任务已在当前页面会话中创建') }
function clearTask(): void { task.value = undefined; pickedStart.value = undefined; pickedDestination.value = undefined; selectionSource?.clear(); routes.value = []; routeSource?.clear(); riskLayersData.value = undefined; riskLayerNames.forEach((name) => { riskSources.get(name)?.clear(); riskLayers.get(name)?.setVisible(false); riskLayerVisibility.value[name] = false }); plannerStatus.value = 'not_started'; plannerError.value = undefined; selectedRouteIndex.value = undefined; recommendedRouteIndex.value = undefined; captainDraft.value = undefined; selectedWaypointId.value = undefined; renderCaptainDraft(); showToast('当前临时任务已取消') }
function selectSampleVessel(): void { selectedVessel.value = sampleVessel; showToast('已选择雪龙2号') }

onBeforeUnmount(() => { window.clearTimeout(toastTimer); environmentClock?.dispose(); unsubscribeState.forEach((unsubscribe) => unsubscribe()); olMap?.un('moveend', refreshViewportLayers); if (draftModify) olMap?.removeInteraction(draftModify); layerManager?.dispose(); routeSource?.clear(); olMap?.setTarget(undefined) })
</script>

<template>
  <main class="bridge-shell">
    <TopStatusBar :task-name="task?.name" :vessel-name="selectedVessel?.name" :planning-time="task?.departureTime?.replace('T', ' ')" :time-label="topTimeLabel" :api-online="apiOnline" :api-status="apiStatus" :planner-status="plannerStatus" :planner-route-count="routes.length" />
    <section class="bridge-workspace">
      <MainNavigation :active="activePanel" @select="activePanel = $event" />
      <aside class="left-workbench">
        <TaskPanel v-if="activePanel === 'task'" :task="task" :pick-target="pickTarget" :picked-start="pickedStart" :picked-destination="pickedDestination" @pick="beginTaskPick" @create="createTask" @clear="clearTask" />
        <VesselPanel v-else-if="activePanel === 'vessel'" :vessel="selectedVessel" @select="selectSampleVessel" @locate="locateVessel" @reset="resetView" />
        <EnvironmentPanel v-else-if="activePanel === 'environment'" :layers="layers" :layer-states="layerStates" :layer-errors="layerErrors" :provider-statuses="providerStatuses" :matched-times="matchedTimes" :time-label="topTimeLabel" :ice-mode="iceMode" :ice-opacity="iceOpacity" :ice-legend="iceLegend" :ice-legend-title="iceLegendTitle" :wave-legend="WAVE_HEIGHT_LEGEND" :northern-grid-visible="northernGridVisible" :northern-grid-loading="northernGridLoading" :risk-layer-visibility="riskLayerVisibility" :risk-layer-labels="riskLayerLabels" @toggle="toggleLayer" @preset="applyPreset" @update:ice-mode="updateIceMode" @update:ice-opacity="updateIceOpacity" @toggle-northern-grid="toggleNorthernGrid" @toggle-risk-layer="toggleRiskLayer" />
        <PlanningPanel v-else-if="activePanel === 'planning'" :task="task" :vessel="selectedVessel" :status="plannerStatus" :planner-routes="routes" :selected-route-index="selectedRouteIndex" :recommended-route-index="recommendedRouteIndex" :planner-error="plannerError" :draft="captainDraft" :selected-waypoint="selectedWaypoint()" :edit-mode="routeEditMode" :can-create-draft="Boolean(task?.start && task?.destination)" :can-undo="undoStack.length > 0" :can-redo="redoStack.length > 0" @open-task="activePanel = 'task'" @plan="runPlanning()" @replan="runPlanning(true)" @select-route="selectPlannerRoute" @create-draft="createManualDraft" @toggle-edit="toggleDraftEdit" @add-waypoint="addDraftWaypoint" @insert-waypoint="insertDraftWaypoint" @delete-waypoint="deleteDraftWaypoint" @undo="undoDraft" @redo="redoDraft" @select-waypoint="selectedWaypointId = $event; renderCaptainDraft()" @toggle-flag="toggleDraftFlag" @unavailable="showToast($event)" />
        <MonitoringPanel v-else-if="activePanel === 'monitoring'" :has-task="Boolean(task)" />
        <EventPanel v-else />
      </aside>
      <section ref="mapStage" class="map-stage">
        <div ref="mapElement" class="map" aria-label="极地航行态势地图"></div>
        <MapToolbar :view-mode="mapViewMode" :polar-level="polarNavigationLevel" :active-tool="activeTool" @view="changeMapView" @tool="handleTool" />
        <div class="map-corner-status"><span>{{ mapViewMode === 'standard' ? '电子海图导航' : '北极战略海图' }}</span><span>海陆边界 · 本地海图</span><span>环境数据 · {{ topTimeLabel }}</span><span>Planner · {{ plannerStatus.toUpperCase() }}</span><span>Captain Draft · {{ captainDraft ? 'VISIBLE / UNCHECKED' : 'NONE' }}</span></div>
        <section v-if="selectedCellView" class="grid-cell-inspector" aria-label="栅格属性">
          <header><strong>{{ selectedCellView.id }}</strong><button type="button" class="text-button" @click="selectedEnvironmentCell = undefined">关闭</button></header>
          <small>{{ selectedCellView.lat.toFixed(3) }}°N · {{ formatLongitude(selectedCellView.lon, 3) }} · 25 km</small>
          <template v-if="selectedCellView.isLand"><div class="grid-cell-obstacle"><span>区域类型</span><b>陆地</b><span>状态</span><b>不可通行</b><span>障碍类型</span><b>{{ selectedCellView.obstacleType ?? 'LAND' }}</b></div><small class="cell-blocked">LAND · 不参与环境风险计算</small></template>
          <template v-else><div class="grid-cell-values"><span>水深 <b>{{ selectedCellView.depth == null ? '-' : `${Number(selectedCellView.depth).toFixed(1)} m` }}</b></span><span>RIO <b>{{ selectedCellView.ice == null ? '-' : Number(selectedCellView.ice).toFixed(2) }}</b></span><span>雾 <b>{{ selectedCellView.fog == null ? '-' : Number(selectedCellView.fog).toFixed(2) }}</b></span><span>风 <b>{{ selectedCellView.wind == null ? '-' : Number(selectedCellView.wind).toFixed(2) }}</b></span><span>浪 <b>{{ selectedCellView.wave == null ? '-' : Number(selectedCellView.wave).toFixed(2) }}</b></span><span>水深风险 <b>{{ selectedCellView.depthRisk == null ? '-' : Number(selectedCellView.depthRisk).toFixed(2) }}</b></span><span>综合 <b>{{ selectedCellView.combined == null ? '-' : Number(selectedCellView.combined).toFixed(2) }}</b></span><span>航速 <b>{{ selectedCellView.speed == null ? '-' : `${Number(selectedCellView.speed).toFixed(1)} kn` }}</b></span></div><small :class="selectedCellView.traversable ? 'cell-safe' : 'cell-blocked'">{{ selectedCellView.traversable ? '可通航' : '浅水/冰障碍' }}</small></template>
        </section>
        <details class="navigation-layer-menu"><summary>Navigation Layers</summary><div><span>Own Ship · NOT CONNECTED</span><span>Historical Track · UNAVAILABLE</span><span>Global Route · UNAVAILABLE</span><span>Recommended Route · {{ recommendedRouteIndex !== undefined ? 'VISIBLE / PROPOSED' : 'NONE' }}</span><span>Candidate Routes · {{ routes.length || 'NONE' }}</span><span>Captain Draft Route · {{ captainDraft ? 'VISIBLE' : 'NONE' }}</span><span>Waypoints · {{ captainDraft ? 'VISIBLE' : 'NONE' }}</span><span>Active Route · NONE</span><span>Risk Grid · {{ riskLayersData ? 'READY' : 'NONE' }}</span><span v-for="name in riskLayerNames" :key="`map-risk-${name}`">{{ riskLayerLabels[name] }} · {{ riskLayerVisibility[name] ? 'VISIBLE' : 'HIDDEN' }}</span><span>Alternatives / XTD / Checked Prefix · UNAVAILABLE</span><span>Risk Zones / AIS / Radar / Dynamic Ice · NOT CONNECTED</span></div></details>
        <div v-if="pickTarget || activeTool" class="pick-mode-banner"><strong>{{ activeTool === 'measure' ? '测距模式' : pickTarget ? '任务选点模式' : '地图选点模式' }}</strong><span>{{ activeTool === 'measure' ? '请依次点击两个位置' : `请点击地图${pickTarget === 'start' ? '设置起点' : pickTarget === 'destination' ? '设置终点' : '查询坐标'}` }}</span><button type="button" @click="pickTarget = undefined; activeTool = undefined; measurePoints.splice(0)">退出</button></div>
        <div ref="wavePopupElement" class="wave-map-popup" :class="{ visible: selectedWave }" role="status"><template v-if="selectedWave"><strong>海浪信息</strong><span>时间：{{ formatEnvironmentTime(selectedWave.matched_time) }}</span><span>有效波高：{{ selectedWave.wave_height.toFixed(2) }} m</span><span>峰值周期：{{ selectedWave.wave_period.toFixed(2) }} s</span><span>波浪来向：{{ selectedWave.wave_direction_from.toFixed(1) }}°</span></template></div>
        <div v-if="toast" class="toast" role="status">{{ toast }}</div>
      </section>
      <ContextPanel :open="rightPanelOpen" :task="task" :vessel="selectedVessel" :coordinate="currentCoordinate" :draft="captainDraft" :selected-waypoint="selectedWaypoint()" :planner-status="plannerStatus" :recommended-route="recommendedRouteIndex !== undefined ? routes[recommendedRouteIndex] : undefined" @toggle="rightPanelOpen = !rightPanelOpen" />
    </section>
    <EnvironmentTimeline :scenario="environmentScenario" :current-time="simulationTime" :time-label="topTimeLabel" :planning-time="task?.departureTime?.replace('T', ' ')" :playing="timelinePlaying" :speed="playbackSpeed" :loading="timelineLoading" @scenario="changeEnvironmentScenario" @seek="seekEnvironmentTime" @step="stepEnvironmentTime" @toggle="toggleEnvironmentPlayback" @speed="setEnvironmentPlaybackSpeed" />
  </main>
</template>
