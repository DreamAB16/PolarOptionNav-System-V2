<script setup lang="ts">
import type { NavigationTask, PlannerRoute, PlanningStatus, VesselSummary } from '../types/bridge'
import type { CaptainDraftRoute, DraftWaypoint } from '../types/navigation'
import { uiStateLabel } from '../services/ui-status'
defineProps<{ open: boolean; task?: NavigationTask; vessel?: VesselSummary; coordinate?: string; draft?: CaptainDraftRoute; selectedWaypoint?: DraftWaypoint; plannerStatus: PlanningStatus; recommendedRoute?: PlannerRoute }>()
const emit = defineEmits<{ toggle: [] }>()
</script>
<template>
  <aside class="context-panel" :class="{ collapsed: !open }">
    <button type="button" class="context-toggle" :aria-label="open ? '收起右侧信息面板' : '展开右侧信息面板'" @click="emit('toggle')">{{ open ? '›' : '‹' }}</button>
    <template v-if="open">
      <header class="context-heading"><div><span class="section-kicker">态势摘要</span><h2>Navigation Overview</h2></div><span class="live-indicator">VIEW ONLY</span></header>
      <section class="context-section"><h3>Navigation Status</h3><dl class="overview-list navigation-priority"><div><dt>Current Position</dt><dd>{{ uiStateLabel('NOT_CONNECTED') }}</dd></div><div><dt>Heading</dt><dd>{{ uiStateLabel('NOT_CONNECTED') }}</dd></div><div><dt>COG</dt><dd>{{ uiStateLabel('NOT_CONNECTED') }}</dd></div><div><dt>STW</dt><dd>{{ uiStateLabel('NOT_CONNECTED') }}</dd></div><div><dt>SOG</dt><dd>{{ uiStateLabel('NOT_CONNECTED') }}</dd></div><div><dt>ROT</dt><dd>{{ uiStateLabel('UNKNOWN') }}</dd></div><div><dt>Next Waypoint</dt><dd>{{ draft && selectedWaypoint ? selectedWaypoint.name : uiStateLabel('NOT_CALCULATED') }}</dd></div><div><dt>Distance to WP</dt><dd>{{ uiStateLabel('NOT_CALCULATED') }}</dd></div><div><dt>XTE</dt><dd>{{ uiStateLabel('NOT_CALCULATED') }}</dd></div><div><dt>ETA</dt><dd>{{ uiStateLabel('NOT_CALCULATED') }}</dd></div></dl></section>
      <section class="context-section"><h3>Environment Status</h3><dl class="overview-list"><div v-for="item in ['Ice Concentration', 'Ice Thickness', 'Ice Type', 'Wind', 'Wave', 'Current', 'Depth']" :key="item"><dt>{{ item }}</dt><dd>{{ uiStateLabel('NOT_CALCULATED') }}</dd></div></dl><p class="context-note">选择真实环境要素后，Inspector 才显示对应采样值与来源。</p></section>
      <section class="context-section"><h3>Route Status</h3><dl class="overview-list"><div><dt>Recommended Route</dt><dd>{{ recommendedRoute ? 'PROPOSED' : 'NONE' }}</dd></div><div><dt>Captain Draft</dt><dd>{{ draft ? 'DRAFT · UNCHECKED' : 'NONE' }}</dd></div><div><dt>Active Route</dt><dd>NONE</dd></div></dl></section>
      <section class="context-section"><h3>System Status</h3><dl class="overview-list"><div><dt>Planner</dt><dd>{{ plannerStatus.toUpperCase() }}</dd></div><div><dt>Environment</dt><dd>{{ uiStateLabel('UNKNOWN') }}</dd></div><div><dt>AIS</dt><dd>{{ uiStateLabel('NOT_CONNECTED') }}</dd></div><div><dt>Radar</dt><dd>{{ uiStateLabel('NOT_CONNECTED') }}</dd></div></dl></section>
      <section class="context-section"><h3>Selection Inspector</h3><div v-if="selectedWaypoint" class="inspector-card"><strong>Waypoint {{ selectedWaypoint.sequence }} · {{ selectedWaypoint.name }}</strong><span>{{ selectedWaypoint.latitude.toFixed(4) }}°, {{ selectedWaypoint.longitude.toFixed(4) }}°</span><span>Lock: {{ selectedWaypoint.locked ? 'ON' : 'OFF' }} · Must Pass: {{ selectedWaypoint.mustPass ? 'ON' : 'OFF' }}</span><span>ETA / Target STW: NOT CALCULATED</span></div><div v-else-if="draft" class="inspector-card"><strong>CaptainDraftRoute</strong><span>Role: CAPTAIN_DRAFT</span><span>Lifecycle: DRAFT</span><span>Validation: UNCHECKED</span><span>Distance: {{ draft.distanceNm.toFixed(1) }} nm</span></div><div v-else class="inspector-card"><strong>Environment Point / Route Leg</strong><span>{{ uiStateLabel('UNAVAILABLE') }}</span></div></section>
      <section class="decision-note"><strong>决策支持声明</strong><p>系统提供环境态势与航行建议。最终航行决策由驾驶员和船长作出。</p></section>
    </template>
  </aside>
</template>
