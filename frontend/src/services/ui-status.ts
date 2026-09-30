import type { UiDataState } from '../types/navigation'

export const UI_STATE_LABELS: Record<UiDataState, string> = {
  NOT_CONNECTED: '未接入',
  NOT_CALCULATED: '未计算',
  UNKNOWN: '未知',
  UNAVAILABLE: '不可用',
}

export function uiStateLabel(state: UiDataState): string {
  return `${UI_STATE_LABELS[state]} · ${state}`
}
