import { Box, Typography } from '@mui/material';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import { COLORS } from '../theme/theme';

/**
 * Shows the improvement_percentage with a colored arrow.
 * Color logic: if higherIsBetter, a positive change is green; otherwise
 * a negative change (i.e. the metric went down, which is good when
 * lower-is-better) is green. Zero change renders neutral gray.
 */
export default function ImprovementIndicator({ value = 0, higherIsBetter = false, unit = '%' }) {
  const rounded = Math.round(Math.abs(value));
  if (rounded === 0) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, minWidth: 40 }}>
        <Typography sx={{ fontSize: 13, fontWeight: 600, color: COLORS.textMuted }}>0</Typography>
        <Typography sx={{ fontSize: 11, color: COLORS.textMuted }}>{unit}</Typography>
      </Box>
    );
  }

  const isIncrease = value > 0;
  const isGood = higherIsBetter ? isIncrease : !isIncrease;
  const color = isGood ? COLORS.accentGreen : COLORS.accentRed;
  const Icon = isIncrease ? ArrowUpwardIcon : ArrowDownwardIcon;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, minWidth: 40 }}>
      <Icon sx={{ fontSize: 15, color }} />
      <Typography sx={{ fontSize: 13, fontWeight: 700, color }}>{rounded}</Typography>
      <Typography sx={{ fontSize: 11, color: COLORS.textMuted }}>{unit}</Typography>
    </Box>
  );
}
