<script setup lang="ts">
import { ref } from 'vue'
import type { LayerKey, LayerState } from '../services/map-layer-manager'
import type { IceDisplayMode } from '../services/ice-layer'
import {
  ENVIRONMENT_LAYER_INFO,
  type EnvironmentLayerKey,
  type EnvironmentProviderStatus,
} from '../services/environment-layer-info'

type RiskLayerName = 'rio' | 'fog' | 'wind' | 'wave' | 'depth' | 'combined'

const props = defineProps<{
  layers: Record<LayerKey, boolean>
  layerStates: Record<LayerKey, LayerState>
  layerErrors: Partial<Record<LayerKey, string>>
  providerStatuses: Partial<Record<EnvironmentLayerKey, EnvironmentProviderStatus>>
  matchedTimes: Partial<Record<EnvironmentLayerKey, string>>
  timeLabel: string
  iceMode: IceDisplayMode
  iceOpacity: number
  iceLegend: ReadonlyArray<{ color: string; label: string }>
  iceLegendTitle: string
  waveLegend: ReadonlyArray<{ color: string; label: string; level: string }>
  northernGridVisible: boolean
  northernGridLoading: boolean
  riskLayerVisibility: Record<RiskLayerName, boolean>
  riskLayerLabels: Record<RiskLayerName, string>
}>()
const emit = defineEmits<{
  toggle: [key: LayerKey]
  preset: [keys: LayerKey[]]
  'update:iceMode': [value: IceDisplayMode]
  'update:iceOpacity': [value: number]
  'toggle-northern-grid': []
  'toggle-risk-layer': [layer: RiskLayerName]
}>()
const legendsOpen = ref(false)
const environmentKeys: Array<{ key: LayerKey; name: string; group: '基础环境' | '动态环境' }> = [
  { key: 'charts', name: '海图', group: '基础环境' }, { key: 'bathymetry', name: '水深', group: '基础环境' },
  { key: 'ice', name: '海冰', group: '动态环境' }, { key: 'wind', name: '风场', group: '动态环境' },
  { key: 'current', name: '海流', group: '动态环境' }, { key: 'wave', name: '海浪', group: '动态环境' },
]
const presets = [
  { label: '基础导航', keys: ['charts', 'bathymetry'] as LayerKey[] },
  { label: '冰情', keys: ['charts', 'ice'] as LayerKey[] },
  { label: '气象海况', keys: ['charts', 'wind', 'wave', 'current'] as LayerKey[] },
  { label: '综合态势', keys: ['charts', 'ice', 'wind', 'current', 'wave'] as LayerKey[] },
]
function status(key: LayerKey): string {
  if (props.layerErrors[key]) return '无当前时间数据'
  const providerStatus = props.providerStatuses[key as EnvironmentLayerKey]
  if (providerStatus === 'pending') return '待接入'
  if (providerStatus === 'not_found') return '数据缺失'
  return ({ idle: providerStatus === 'ready' ? '可用' : '未加载', loading: '加载中', ready: '已显示', error: '无当前时间数据' } as const)[props.layerStates[key]]
}
function statusClass(key: LayerKey): string {
  const value = status(key)
  if (value === '已显示' || value === '可用') return 'ready'
  if (value === '加载中') return 'loading'
  if (value === '未加载') return 'idle'
  return 'error'
}
function layerInfo(key: LayerKey) {
  return ENVIRONMENT_LAYER_INFO[key as EnvironmentLayerKey]
}
function matchedLabel(key: LayerKey): string {
  const value = props.matchedTimes[key as EnvironmentLayerKey]
  return value ? `${new Date(value).toISOString().slice(0, 16).replace('T', ' ')} UTC` : '图层加载后显示'
}
</script>

<template>
  <section class="module-panel">
    <header class="panel-heading"><div><span class="section-kicker">环境</span><h2>环境态势</h2></div><span class="time-chip">{{ timeLabel }}</span></header>
    <div class="preset-grid" aria-label="环境快速预设"><button v-for="presetItem in presets" :key="presetItem.label" type="button" @click="emit('preset', presetItem.keys)">{{ presetItem.label }}</button></div>
    <section class="environment-grid-control">
      <div><strong>东北航道 25 km 栅格</strong><small>固定研究区网格 · 点击单元查看属性</small></div>
      <button type="button" class="secondary-button" :disabled="northernGridLoading" @click="emit('toggle-northern-grid')">{{ northernGridLoading ? '加载中…' : northernGridVisible ? '隐藏栅格' : '显示栅格' }}</button>
    </section>
    <section class="environment-grid-layers">
      <header><strong>栅格风险图层</strong><small>{{ northernGridVisible ? '可独立切换' : '请先显示栅格' }}</small></header>
      <div class="risk-layer-toggles">
        <button v-for="name in (['rio', 'fog', 'wind', 'wave', 'depth', 'combined'] as RiskLayerName[])" :key="name" type="button" :class="{ active: riskLayerVisibility[name] }" :aria-pressed="riskLayerVisibility[name]" :disabled="!northernGridVisible" @click="emit('toggle-risk-layer', name)">{{ riskLayerLabels[name] }}</button>
      </div>
    </section>
    <template v-for="group in ['基础环境', '动态环境'] as const" :key="group">
      <h3 class="group-title">{{ group }}</h3>
      <div v-for="item in environmentKeys.filter((entry) => entry.group === group)" :key="item.key" class="environment-row">
        <div class="environment-summary" :title="layerInfo(item.key) ? `${layerInfo(item.key).source} · ${layerInfo(item.key).resolution} · ${layerInfo(item.key).cadence}` : undefined">
          <strong>{{ item.name }}</strong>
          <template v-if="layerInfo(item.key)">
            <small class="environment-source">{{ layerInfo(item.key).source }}</small>
            <small>{{ layerInfo(item.key).resolution }} · {{ layerInfo(item.key).cadence }}</small>
            <small v-if="item.key !== 'bathymetry'">匹配：{{ matchedLabel(item.key) }}</small>
            <small>质量：UNKNOWN</small>
          </template>
          <template v-else><small>Source：UNKNOWN</small><small>Update Time：UNKNOWN · Quality：UNKNOWN</small></template>
        </div>
        <span class="layer-health" :class="statusClass(item.key)">{{ status(item.key) }}</span>
        <button type="button" class="switch" :class="{ on: layers[item.key] }" :aria-label="`${layers[item.key] ? '关闭' : '开启'}${item.name}`" @click="emit('toggle', item.key)"><i></i></button>
      </div>
      <div v-if="group === '动态环境' && layers.ice" class="sub-controls">
        <label>海冰显示变量<select :value="iceMode" @change="emit('update:iceMode', ($event.target as HTMLSelectElement).value as IceDisplayMode)"><option value="concentration">海冰密集度</option><option value="thickness">海冰厚度</option></select></label>
        <label>海冰透明度 <output>{{ iceOpacity.toFixed(1) }}</output><input :value="iceOpacity" type="range" min="0.3" max="1" step="0.05" @input="emit('update:iceOpacity', Number(($event.target as HTMLInputElement).value))" /></label>
      </div>
    </template>
    <button v-if="layers.ice || layers.wave" type="button" class="collapse-button" @click="legendsOpen = !legendsOpen">图例 <span>{{ legendsOpen ? '收起' : '展开' }}</span></button>
    <div v-if="legendsOpen" class="legend-stack">
      <section v-if="layers.ice"><strong>{{ iceLegendTitle }}</strong><div class="legend-gradient" :class="`ice-gradient--${iceMode}`"></div><div class="legend-labels"><span v-for="entry in iceLegend" :key="entry.label">{{ entry.label }}</span></div></section>
      <section v-if="layers.wave"><strong>海浪有效波高 Hs</strong><div class="wave-legend"><span v-for="entry in waveLegend" :key="entry.label"><i :style="{ background: entry.color }"></i>{{ entry.label }} {{ entry.level }}</span></div></section>
    </div>
    <section class="future-features"><header><strong>Unified Environment Inspector</strong><span>FUTURE</span></header><dl class="data-list compact"><div><dt>Ice Type / Composition</dt><dd>UNKNOWN</dd></div><div><dt>Ice Drift</dt><dd>NOT CONNECTED</dd></div><div><dt>Unified Point Inspect</dt><dd>NOT CALCULATED</dd></div><div><dt>Data Quality</dt><dd>UNAVAILABLE</dd></div><div><dt>Uncertainty</dt><dd>UNAVAILABLE</dd></div></dl><small>现有 Wave 点击查询继续使用真实数据；统一环境查询尚未接入。</small></section>
  </section>
</template>
