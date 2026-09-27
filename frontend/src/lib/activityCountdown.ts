export interface ActivityCountdownStatus {
  active: boolean
  activityId?: string | null
  etaSeconds: number | null
}

export interface ActivityCountdownState {
  activityId: string | null
  etaSeconds: number | null
  value: number | null
}

export function getActivityCountdown(
  state: ActivityCountdownState,
  status: ActivityCountdownStatus | null,
): number | null {
  if (!status?.active || status.etaSeconds == null) return null
  const activityId = status.activityId ?? null
  return state.activityId === activityId && state.etaSeconds === status.etaSeconds
    ? state.value
    : Math.round(status.etaSeconds)
}

export function tickActivityCountdown(
  previous: ActivityCountdownState,
  status: ActivityCountdownStatus,
): ActivityCountdownState {
  const activityId = status.activityId ?? null
  const current =
    previous.activityId === activityId && previous.etaSeconds === status.etaSeconds
      ? previous.value
      : Math.round(status.etaSeconds ?? 0)
  return {
    activityId,
    etaSeconds: status.etaSeconds,
    value: current == null || current <= 1 ? 0 : current - 1,
  }
}
