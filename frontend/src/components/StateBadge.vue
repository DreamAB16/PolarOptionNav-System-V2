<script setup lang="ts">
import type { UiDataState } from '../types/navigation'
import { uiStateLabel } from '../services/ui-status'
defineProps<{ state: UiDataState; compact?: boolean }>()
</script>
<template><span class="state-badge" :class="`state-${state.toLowerCase()}`" :title="state">{{ compact ? state : uiStateLabel(state) }}</span></template>
