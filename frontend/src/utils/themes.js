export const THEMES = [
  { id: "theme-dusk", name: "Dusk", description: "Soft charcoal and lavender", mode: "dark", swatches: ["#15161b", "#272a33", "#b8a1f1"] },
  { id: "theme-daylight", name: "Daylight", description: "Soft white and indigo", mode: "light", swatches: ["#fcfcfe", "#eceef9", "#4f5abd"] },
  { id: "theme-midnight", name: "Midnight", description: "Deep charcoal and ice blue", mode: "dark", swatches: ["#0d1015", "#1c232e", "#8bc7e9"] },
];

const LEGACY_THEMES = {
  "theme-cyberpunk": "theme-midnight",
  "theme-vaporwave": "theme-dusk",
  "theme-nord": "theme-midnight",
  "theme-dark-elegance": "theme-dusk",
  "theme-light-mode": "theme-daylight",
};

export const THEME_CLASSES = [...THEMES.map(({ id }) => id), ...Object.keys(LEGACY_THEMES)];

export function resolveTheme(value) {
  if (typeof value !== "string") return "theme-dusk";
  return THEMES.some(({ id }) => id === value) ? value : Object.hasOwn(LEGACY_THEMES, value) ? LEGACY_THEMES[value] : "theme-dusk";
}
