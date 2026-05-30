export const SLEEP_STAGE_COLORS: Record<string, string> = {
  deep: "var(--sleep-stage-deep)",
  light: "var(--sleep-stage-light)",
  rem: "var(--sleep-stage-rem)",
  awake: "var(--sleep-stage-awake)",
  unknown: "var(--sleep-stage-unknown)",
};

export function sleepStageColor(stage: string): string {
  return SLEEP_STAGE_COLORS[stage] || SLEEP_STAGE_COLORS.unknown;
}
