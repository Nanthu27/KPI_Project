import { createTheme } from '@mui/material/styles';

/**
 * Design tokens lifted directly from the provided screenshots:
 *  - Primary header bars / buttons: deep slate-purple (#545379)
 *  - Page background: light gray (#ECECEC)
 *  - Card surfaces: white, soft shadow, 12px radius
 *  - Slider "benchmark band": purple (#7A5AF8)
 *  - Up/down indicators: green (#2ECC71) / red (#E74C3C)
 */
export const COLORS = {
  primary: '#545379',
  primaryDark: '#46455F',
  background: '#ECECEC',
  panelBackground: '#E4E4EA',
  card: '#FFFFFF',
  border: '#D6D6D6',
  accentGreen: '#2ECC71',
  accentRed: '#E15554',
  accentPurple: '#7A5AF8',
  trackGray: '#D9D9DE',
  triangle: '#3F3D56',
  textPrimary: '#2B2A3D',
  textSecondary: '#6B6A80',
  textMuted: '#9492A8',
};

const theme = createTheme({
  palette: {
    primary: {
      main: COLORS.primary,
      dark: COLORS.primaryDark,
      contrastText: '#FFFFFF',
    },
    success: { main: COLORS.accentGreen },
    error: { main: COLORS.accentRed },
    background: {
      default: COLORS.background,
      paper: COLORS.card,
    },
    text: {
      primary: COLORS.textPrimary,
      secondary: COLORS.textSecondary,
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontWeight: 800 },
    h6: { fontWeight: 700 },
    subtitle1: { fontWeight: 600 },
    body2: { fontWeight: 500 },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: 8,
          boxShadow: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
  },
});

export default theme;
