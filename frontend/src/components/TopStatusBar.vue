<script setup lang="ts">
import { ref } from 'vue'
import type { PlanningStatus } from '../types/bridge'

defineProps<{
  taskName?: string
  vesselName?: string
  timeLabel: string
  planningTime?: string
  apiOnline: boolean
  apiStatus: string
  plannerStatus: PlanningStatus
  plannerRouteCount: number
}>()

const statusOpen = ref(false)
</script>

<template>
  <header class="top-status-bar">
    <div class="brand-block">
      <div class="brand-mark">P</div>
      <div><strong>PolarOptionNav</strong><span>极地船舶环境感知与数据融合</span></div>
    </div>
    <div class="mission-status">
      <div><span>当前任务</span><strong>{{ taskName || '未加载任务' }}</strong></div>
      <div><span>当前船舶</span><strong>{{ vesselName || '未选择船舶' }}</strong></div>
      <div class="clock"><span>Planning Time</span><strong>{{ planningTime || '--' }}</strong></div>
      <div class="clock"><span>View Time</span><strong>{{ timeLabel }}</strong></div>
    </div>
    <div class="service-status">
      <div><span>规划器</span><strong :class="plannerStatus === 'completed' ? 'ready-state' : 'muted-state'">{{ plannerStatus.toUpperCase() }}</strong></div>
      <div><span>推荐路线</span><strong :class="plannerRouteCount ? 'ready-state' : 'muted-state'">{{ plannerRouteCount ? `${plannerRouteCount} 条候选` : 'NONE' }}</strong></div>
      <div><span>Near-field</span><strong class="muted-state">未接入</strong></div>
      <div><span>仿真</span><strong class="muted-state">未连接</strong></div>
      <button type="button" class="status-trigger" :aria-expanded="statusOpen" @click="statusOpen = !statusOpen">
        <i :class="{ online: apiOnline }"></i><span>数据服务</span><strong>{{ apiOnline ? '正常' : '不可用' }}</strong>
      </button>
      <section v-if="statusOpen" class="status-popover" aria-label="系统状态详情">
        <header><strong>系统状态</strong><button type="button" @click="statusOpen = false">关闭</button></header>
        <dl>
          <div><dt>后端服务</dt><dd :class="apiOnline ? 'ready' : 'error'">{{ apiStatus }}</dd></div>
          <div><dt>环境时间</dt><dd class="ready">正常</dd></div>
          <div v-for="source in ['海冰', '风场', '海流', '海浪', '水深']" :key="source"><dt>{{ source }}</dt><dd class="ready">可用</dd></div>
          <div><dt>规划服务</dt><dd :class="plannerStatus === 'completed' ? 'ready' : plannerStatus === 'failed' ? 'error' : ''">{{ plannerStatus.toUpperCase() }}</dd></div>
          <div><dt>船舶实时数据 / AIS</dt><dd>未接入</dd></div>
        </dl>
      </section>
    </div>
  </header>
</template>
