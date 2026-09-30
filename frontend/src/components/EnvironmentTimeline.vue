<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import {
  ENVIRONMENT_SCENARIOS,
  scenarioHour,
  scenarioHourCount,
  timestampAtScenarioHour,
  type EnvironmentScenario,
  type PlaybackSpeed,
} from '../services/environment-time'

const props = defineProps<{
  scenario: EnvironmentScenario
  currentTime: string
  timeLabel: string
  planningTime?: string
  playing: boolean
  speed: PlaybackSpeed
  loading?: boolean
}>()
const emit = defineEmits<{
  scenario: [scenario: EnvironmentScenario]
  seek: [timestamp: string]
  step: [direction: -1 | 1]
  toggle: []
  speed: [speed: PlaybackSpeed]
}>()

const hour = computed(() => scenarioHour(props.currentTime, props.scenario))
const maximumHour = computed(() => scenarioHourCount(props.scenario))
let seekTimer: ReturnType<typeof setTimeout> | undefined
function scheduleSeek(value: number): void {
  if (seekTimer !== undefined) clearTimeout(seekTimer)
  seekTimer = setTimeout(() => emit('seek', timestampAtScenarioHour(props.scenario, value)), 120)
}
onBeforeUnmount(() => { if (seekTimer !== undefined) clearTimeout(seekTimer) })
</script>

<template>
  <footer class="environment-timeline">
    <div class="timeline-title">
      <span>Environment Timeline</span>
      <strong>{{ loading ? '环境图层更新中…' : playing ? `播放中 · ${speed}×` : '已暂停' }}</strong>
    </div>
    <div class="timeline-times"><p><b>View Time</b><span>{{ timeLabel }}</span></p><p><b>Planning Time</b><span>{{ planningTime || '--' }}</span></p></div>
    <div class="timeline-scenario">
      <button v-for="(range, key) in ENVIRONMENT_SCENARIOS" :key="key" type="button" :class="{ active: scenario === key }" @click="emit('scenario', key)">{{ range.label }}</button>
    </div>
    <div class="timeline-range">
      <input type="range" min="0" :max="maximumHour" step="1" :value="hour" aria-label="环境时间" @input="scheduleSeek(Number(($event.target as HTMLInputElement).value))" />
      <span>{{ timeLabel }}</span>
    </div>
    <div class="timeline-controls">
      <button type="button" title="上一个小时" @click="emit('step', -1)">◀</button>
      <button type="button" class="play-button" :title="playing ? '暂停' : '播放'" @click="emit('toggle')">{{ playing ? '⏸ 暂停' : '▶ 播放' }}</button>
      <button type="button" title="下一个小时" @click="emit('step', 1)">▶</button>
      <select :value="speed" aria-label="播放速度" @change="emit('speed', Number(($event.target as HTMLSelectElement).value) as PlaybackSpeed)"><option :value="1">1×</option><option :value="2">2×</option><option :value="5">5×</option></select>
    </div>
  </footer>
</template>
