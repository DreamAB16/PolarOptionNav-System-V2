<script setup lang="ts">
import type { MapViewMode, PolarNavigationLevel } from '../map/polar-view'
defineProps<{ viewMode: MapViewMode; polarLevel: PolarNavigationLevel; activeTool?: string }>()
const emit = defineEmits<{
  view: [mode: MapViewMode, level?: PolarNavigationLevel]
  tool: [tool: 'locate' | 'measure' | 'coordinate' | 'pick' | 'info' | 'fullscreen' | 'reset']
}>()
</script>
<template>
  <div class="map-controls">
    <div class="view-switcher" aria-label="地图视图模式">
      <button type="button" :class="{ active: viewMode === 'standard' }" @click="emit('view', 'standard')">普通导航</button>
      <button type="button" :class="{ active: viewMode === 'polar' && polarLevel === 'strategic' }" @click="emit('view', 'polar', 'strategic')">北极战略</button>
    </div>
    <div class="tool-strip" aria-label="地图工具">
      <button type="button" title="回到船位" @click="emit('tool', 'locate')">船位</button>
      <button type="button" title="测量两点间大圆距离" :class="{ active: activeTool === 'measure' }" @click="emit('tool', 'measure')">测距</button>
      <button type="button" title="点击地图查询坐标" :class="{ active: activeTool === 'coordinate' }" @click="emit('tool', 'coordinate')">坐标</button>
      <button type="button" title="地图选点" :class="{ active: activeTool === 'pick' }" @click="emit('tool', 'pick')">选点</button>
      <button type="button" title="查看图层信息" @click="emit('tool', 'info')">图层</button>
      <button type="button" title="切换地图全屏" @click="emit('tool', 'fullscreen')">全屏</button>
      <button type="button" title="重置当前视图" @click="emit('tool', 'reset')">重置</button>
    </div>
  </div>
</template>
