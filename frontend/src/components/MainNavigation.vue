<script setup lang="ts">
import type { PrimaryPanel } from '../types/bridge'

defineProps<{ active: PrimaryPanel }>()
const emit = defineEmits<{ select: [panel: PrimaryPanel] }>()

const items: Array<{ id: PrimaryPanel; icon: string; label: string }> = [
  { id: 'task', icon: '任', label: '任务' },
  { id: 'vessel', icon: '船', label: '船舶' },
  { id: 'environment', icon: '环', label: '环境' },
  { id: 'planning', icon: '规', label: '规划' },
  { id: 'monitoring', icon: '监', label: '监控' },
  { id: 'events', icon: '事', label: '事件' },
]
</script>

<template>
  <nav class="primary-nav" aria-label="系统主功能">
    <button v-for="item in items" :key="item.id" type="button" :class="{ active: active === item.id }" @click="emit('select', item.id)">
      <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
      <span>{{ item.label }}</span>
    </button>
  </nav>
</template>
