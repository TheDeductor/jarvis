// temperatureColor.ts  —  Maps temperature to a CSS color for room visualization.
//
// Cold  (≤18°C) → blue
// Comfort (22°C) → neutral green-teal
// Hot  (≥32°C) → red
//
// Uses HSL interpolation for a smooth continuous gradient.
// NOT a standard colorimetry specification — design choice for visual clarity.

export function temperatureToColor(tempC: number): string {
  // Clamp to display range
  const t = Math.max(14, Math.min(40, tempC));

  // Map temperature to hue: blue (240°) → teal (170°) → green (120°) → red (0°)
  // Range [14, 40] → hue [240, 0]
  const hue = 240 - ((t - 14) / (40 - 14)) * 240;

  // Saturation and lightness vary for visual pop
  const saturation = 50 + Math.abs(t - 22) * 1.5;  // more saturated when extreme
  const lightness  = 35 + Math.max(0, (22 - Math.abs(t - 22))) * 0.5;

  return `hsl(${hue.toFixed(0)}, ${Math.min(saturation, 75).toFixed(0)}%, ${lightness.toFixed(0)}%)`;
}

// Returns a text colour (white or dark) contrasting against the room background.
export function contrastColor(tempC: number): string {
  const t = Math.max(14, Math.min(40, tempC));
  // Light background near comfort, dark background at extremes
  return t < 32 && t > 18 ? '#1a1a2e' : '#f0f4ff';
}
