import { Box, Typography } from '@mui/material';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import { COLORS } from '../theme/theme';

/**
 * Arrow indicator for KPI metric cards.
 *
 * Arrow logic:
 *   currentValue > savedValue → Up arrow
 *   currentValue < savedValue → Down arrow
 *   equal                     → Up arrow (neutral, no color emphasis)
 *
 * Color logic (Higher the Better / Lower the Better):
 *   Higher the Better:
 *     Increased → Green  |  Decreased → Red
 *   Lower the Better:
 *     Increased → Red    |  Decreased → Green
 *
 * Props:
 *   currentValue   – the value currently shown (may include local slider change)
 *   savedValue     – the value last fetched from DB (= default / previous)
 *   higherIsBetter – boolean from the metric record
 *   unit           – display suffix (default '%')
 */
export default function ImprovementIndicator({
  currentValue = 0,
  savedValue = 0,
  higherIsBetter = true,
  unit = '%',
}) {
  const increased = currentValue > savedValue;
  const decreased = currentValue < savedValue;

  const ArrowIcon = increased ? ArrowUpwardIcon : ArrowDownwardIcon;

  let color = COLORS.textMuted; // neutral when equal
  if (increased) {
    color = higherIsBetter ? COLORS.accentGreen : COLORS.accentRed;
  } else if (decreased) {
    color = higherIsBetter ? COLORS.accentRed : COLORS.accentGreen;
  }

  // Display the % change rounded to 1 decimal
  const changePct =
    savedValue !== 0
      ? Math.abs(((currentValue - savedValue) / savedValue) * 100).toFixed(1)
      : Math.abs(currentValue - savedValue).toFixed(1);

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <ArrowIcon sx={{ color, fontSize: 16 }} />
      <Typography sx={{ color, fontWeight: 700, fontSize: 12 }}>
        {changePct}
        {unit}
      </Typography>
    </Box>
  );
}
