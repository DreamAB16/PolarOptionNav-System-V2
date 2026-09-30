import type { LayerKey, LayerState } from './services/map-layer-manager'

export const LAYER_LABELS: Record<LayerKey, string> = {
  charts: '海图',
  bathymetry: '水深',
  ice: '海冰',
  wind: '风场',
  current: '海流',
  wave: '海浪',
  route: '规划航线',
  vessel: '船舶',
}

export const LAYER_STATE_LABELS: Record<LayerState, string> = {
  idle: '未加载',
  loading: '加载中',
  ready: '正常',
  error: '异常',
}
