/**
 * Pi Agents — dark terminal/AI aesthetic.
 * Both light and dark keys use the same dark palette so the app
 * always renders in dark mode regardless of the device setting.
 */

const darkPalette = {
  // Legacy aliases
  text: '#FAFAFA',
  tint: '#3B82F6',

  // Core surfaces
  background: '#09090B',
  foreground: '#FAFAFA',

  // Cards / elevated surfaces
  card: '#18181B',
  cardForeground: '#FAFAFA',

  // Primary action
  primary: '#3B82F6',
  primaryForeground: '#FFFFFF',

  // Secondary surfaces
  secondary: '#27272A',
  secondaryForeground: '#FAFAFA',

  // Muted
  muted: '#27272A',
  mutedForeground: '#A1A1AA',

  // Accent
  accent: '#27272A',
  accentForeground: '#FAFAFA',

  // Destructive
  destructive: '#EF4444',
  destructiveForeground: '#FFFFFF',

  // Borders and inputs
  border: '#3F3F46',
  input: '#27272A',

  // Agent accent colors
  dataAccent: '#3B82F6',     // electric blue  — Data
  cortonaAccent: '#A78BFA',  // violet         — Cortona
  jarvisAccent: '#FBBF24',   // amber          — Jarvis
  councilAccent: '#2DD4BF',  // teal           — Council
};

const colors = {
  light: darkPalette,
  dark: darkPalette,
  radius: 14,
};

export default colors;
