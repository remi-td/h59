export type DashboardTheme = "parchment" | "atlas" | "studio";

export const DASHBOARD_THEMES: Record<
  DashboardTheme,
  {
    label: string;
    description: string;
  }
> = {
  parchment: {
    label: "Parchment",
    description: "Warm editorial neutrals with brass and pine accents.",
  },
  atlas: {
    label: "Atlas",
    description: "Cool slate surfaces with alpine greens and coral highlights.",
  },
  studio: {
    label: "Studio",
    description: "Crisp gallery whites with ink blues and citrus contrast.",
  },
};

export const DEFAULT_DASHBOARD_THEME: DashboardTheme = "parchment";
