<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { NavigationTask, PickTarget, TaskDraft } from '../types/bridge'

const props = defineProps<{ task?: NavigationTask; pickTarget: PickTarget; pickedStart?: TaskDraft['start']; pickedDestination?: TaskDraft['destination'] }>()
const emit = defineEmits<{
  create: [draft: TaskDraft]
  pick: [target: Exclude<PickTarget, undefined>]
  clear: []
}>()

const draft = reactive<TaskDraft>({
  name: '', departureTime: '2025-02-15T12:00', planningMode: 'balanced', notes: '', tacticalHorizonNm: 50, globalRouteContext: '', captainConstraints: '',
})
const editing = reactive({ active: false })

watch(() => props.task, (task) => {
  if (!task) return
  Object.assign(draft, task)
}, { immediate: true })
watch(() => props.pickedStart, (point) => { if (point) draft.start = point })
watch(() => props.pickedDestination, (point) => { if (point) draft.destination = point })

function submit(): void {
  if (!draft.name.trim()) return
  emit('create', { ...draft })
  editing.active = false
}
</script>

<template>
  <section class="module-panel">
    <header class="panel-heading"><div><span class="section-kicker">航行任务</span><h2>任务工作区</h2></div><span class="dev-badge">界面预览</span></header>

    <div v-if="!task && !editing.active" class="empty-state prominent">
      <span class="empty-symbol">◇</span><strong>当前未加载航行任务</strong>
      <p>创建任务后可在地图上设置起终点，并进入规划准备流程。</p>
      <button type="button" class="primary-button" @click="editing.active = true">新建任务</button>
      <button type="button" class="secondary-button" disabled title="任务服务尚未接入">打开任务</button>
      <div class="button-grid"><button type="button" class="secondary-button" disabled title="后端任务持久化尚未实现">Save</button><button type="button" class="secondary-button" disabled title="后端任务持久化尚未实现">Load</button><button type="button" class="secondary-button" disabled title="后端任务持久化尚未实现">Duplicate</button><button type="button" class="secondary-button" disabled title="后端任务持久化尚未实现">Archive</button></div>
      <small>任务服务尚未接入，当前任务仅保存在本次页面会话中。</small>
    </div>

    <form v-else-if="editing.active" class="form-stack" @submit.prevent="submit">
      <label>任务名称<input v-model="draft.name" required placeholder="例如：东北航道冬季航行" /></label>
      <div class="point-field">
        <span>起点</span><strong>{{ draft.start?.name || '未设置' }}</strong>
        <button type="button" :class="{ active: pickTarget === 'start' }" @click="emit('pick', 'start')">{{ pickTarget === 'start' ? '请点击地图' : '地图选择' }}</button>
      </div>
      <div class="point-field">
        <span>终点</span><strong>{{ draft.destination?.name || '未设置' }}</strong>
        <button type="button" :class="{ active: pickTarget === 'destination' }" @click="emit('pick', 'destination')">{{ pickTarget === 'destination' ? '请点击地图' : '地图选择' }}</button>
      </div>
      <label>计划出发时间<input v-model="draft.departureTime" type="datetime-local" /></label>
      <label>船舶<select v-model="draft.vesselId"><option value="">暂不选择</option><option value="xuelong2">雪龙2号（PC3）</option></select></label>
      <label>规划偏好<select v-model="draft.planningMode"><option value="fastest">最快航行</option><option value="lowest_risk">最低风险</option><option value="balanced">综合权衡</option></select></label>
      <label>战术规划范围<input v-model.number="draft.tacticalHorizonNm" type="number" min="1" step="1" /> nm</label>
      <label>Global Route Context<textarea v-model="draft.globalRouteContext" rows="2" placeholder="未接入全局航线服务"></textarea></label>
      <label>Captain Constraints<textarea v-model="draft.captainConstraints" rows="2" placeholder="可选，当前仅记录界面输入"></textarea></label>
      <label>备注<textarea v-model="draft.notes" rows="3" placeholder="选填"></textarea></label>
      <div class="button-row"><button class="primary-button" type="submit">创建任务</button><button class="secondary-button" type="button" @click="editing.active = false">取消</button></div>
    </form>

    <div v-else class="detail-stack">
      <div class="summary-card"><span>当前任务</span><strong>{{ task?.name }}</strong><small>会话内临时任务 · 尚未接入任务服务</small></div>
      <dl class="data-list">
        <div><dt>起点</dt><dd>{{ task?.start?.name || '未设置' }}</dd></div>
        <div><dt>终点</dt><dd>{{ task?.destination?.name || '未设置' }}</dd></div>
        <div><dt>计划出发</dt><dd>{{ task?.departureTime.replace('T', ' ') }} UTC</dd></div>
        <div><dt>规划偏好</dt><dd>{{ task?.planningMode === 'fastest' ? '最快航行' : task?.planningMode === 'lowest_risk' ? '最低风险' : '综合权衡' }}</dd></div>
        <div><dt>战术范围</dt><dd>{{ task?.tacticalHorizonNm || 50 }} nm</dd></div>
      </dl>
      <button class="secondary-button wide" type="button" @click="editing.active = true">编辑任务</button>
      <div class="button-grid"><button class="secondary-button" type="button" disabled title="后端任务持久化尚未实现">Save</button><button class="secondary-button" type="button" disabled title="后端任务持久化尚未实现">Load</button><button class="secondary-button" type="button" disabled title="后端任务持久化尚未实现">Duplicate</button><button class="secondary-button" type="button" disabled title="后端任务持久化尚未实现">Archive</button></div>
      <button class="text-button" type="button" @click="emit('clear')">取消当前任务</button>
    </div>
  </section>
</template>
