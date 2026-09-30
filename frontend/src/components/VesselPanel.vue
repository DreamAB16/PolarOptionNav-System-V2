<script setup lang="ts">
import type { VesselSummary } from '../types/bridge'
import StateBadge from './StateBadge.vue'
defineProps<{ vessel?: VesselSummary }>()
const emit = defineEmits<{ select: []; locate: []; reset: [] }>()
</script>

<template>
  <section class="module-panel">
    <header class="panel-heading"><div><span class="section-kicker">船舶</span><h2>船舶资料</h2></div><span class="dev-badge">公开参数</span></header>
    <div v-if="!vessel" class="empty-state prominent"><span class="empty-symbol">△</span><strong>未选择船舶</strong><p>选择船舶以完善任务条件。实时船位与 AIS 尚未接入。</p><button class="primary-button" type="button" @click="emit('select')">选择船舶</button></div>
    <div v-else class="detail-stack">
      <div class="vessel-card"><div class="ship-silhouette">▰</div><div><strong>{{ vessel.name }}</strong><span>{{ vessel.type }}</span></div><span class="ice-class">{{ vessel.iceClass }}</span></div>
      <p class="inline-notice">公开设计参数 · 非实时船舶数据</p>
      <section class="subsection"><header><strong>Vessel Capability</strong><span>STATIC / EVIDENCE-BACKED</span></header>
        <dl class="data-list two-column">
          <div><dt>船舶名称</dt><dd>{{ vessel.name }}</dd></div><div><dt>船舶类型</dt><dd>{{ vessel.type }}</dd></div>
          <div><dt>PC等级</dt><dd>{{ vessel.iceClass }}</dd></div><div><dt>长度 / 宽度</dt><dd>{{ vessel.length }} / {{ vessel.beam }} m</dd></div>
          <div><dt>设计吃水</dt><dd>{{ vessel.draft }} m</dd></div><div><dt>排水量</dt><dd>{{ vessel.displacement == null ? 'UNKNOWN' : `${vessel.displacement} t` }}</dd></div>
          <div><dt>推进方式</dt><dd>{{ vessel.propulsion || 'UNKNOWN' }}</dd></div><div><dt>推进功率</dt><dd>{{ vessel.propulsionPowerMw == null ? 'UNKNOWN' : `${vessel.propulsionPowerMw} MW` }}</dd></div>
          <div><dt>公开参考航速</dt><dd>{{ vessel.maxSpeed }} kn</dd></div><div><dt>冰况能力</dt><dd>{{ vessel.iceThickness == null ? 'UNKNOWN' : `${vessel.iceThickness} m冰` }}</dd></div>
          <div><dt>机动能力</dt><dd>UNKNOWN</dd></div><div><dt>证据 / 来源</dt><dd>VESSEL_DATA / profile</dd></div>
        </dl>
      </section>
      <section class="subsection live-state"><header><strong>Live Navigation State</strong><StateBadge state="NOT_CONNECTED" /></header>
        <dl class="data-list two-column">
          <div><dt>Heading</dt><dd>NOT CONNECTED</dd></div><div><dt>COG</dt><dd>NOT CONNECTED</dd></div>
          <div><dt>STW</dt><dd>NOT CONNECTED</dd></div><div><dt>SOG</dt><dd>NOT CONNECTED</dd></div>
          <div><dt>ROT</dt><dd>UNKNOWN</dd></div><div><dt>Navigation Timestamp</dt><dd>NOT CONNECTED</dd></div>
          <div><dt>Latitude</dt><dd>NOT CONNECTED</dd></div><div><dt>Longitude</dt><dd>NOT CONNECTED</dd></div>
          <div><dt>Data Source</dt><dd>NOT CONNECTED</dd></div><div><dt>Data Quality</dt><dd>UNKNOWN</dd></div>
        </dl>
      </section>
      <div class="button-grid"><button class="secondary-button" type="button" @click="emit('select')">选择船舶</button><button class="secondary-button" type="button" disabled>编辑参数</button><button class="secondary-button" type="button" @click="emit('locate')">定位到船舶</button><button class="secondary-button" type="button" @click="emit('reset')">重置视图</button></div>
      <small class="helper-text">编辑参数与实时船舶数据将在船舶服务接入后启用。</small>
    </div>
  </section>
</template>
