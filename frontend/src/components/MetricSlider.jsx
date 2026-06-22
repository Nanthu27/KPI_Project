import { Box, Typography } from '@mui/material';
import { COLORS } from '../theme/theme';

/**
 * Custom slider visual matching the KPI Simulator screenshots exactly:
 *
 *   [low]     [band_min ▲ target_value]            [high]
 *   |----------|========purple band========|----------|
 *                  ▲ (dark triangle = current value position)
 *                       [bold current value]
 *
 * - Gray track spans min_value..max_value.
 * - Purple "benchmark band" spans from band_min to target_value — this is
 *   an explicit, independently-set range (NOT derived from current value
 *   or higher_is_better); it simply highlights the target/benchmark zone
 *   for that metric, wherever the data says it is.
 * - A dark triangle marks current_value's position along the track.
 * - Two small numbers sit just above the band: band_min and target_value.
 * - min/max are printed at the track's far left/right beneath it, with
 *   the bold current value centered underneath the triangle.
 */
export default function MetricSlider({
  minValue = 0,
  bandMin = 0,
  targetValue = 0,
  maxValue = 100,
  currentValue = 0,
}) {
  const clamp = (v) => Math.min(Math.max(v, minValue), maxValue);
  const range = Math.max(maxValue - minValue, 0.0001);
  const pct = (v) => ((clamp(v) - minValue) / range) * 100;

  const currentPct = pct(currentValue);
  const bandStartPct = pct(Math.min(bandMin, targetValue));
  const bandEndPct = pct(Math.max(bandMin, targetValue));

  const formatVal = (v) => {
    if (Number.isInteger(v)) return v;
    return Math.round(v * 100) / 100;
  };

  return (
    <Box sx={{ width: '100%', mt: 1 }}>
      {/* Band boundary callouts above the track */}
      <Box sx={{ position: 'relative', height: 18, mb: 0.25 }}>
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            left: `${bandStartPct}%`,
            transform: 'translateX(-50%)',
            fontSize: 12,
            color: COLORS.textSecondary,
            fontWeight: 500,
            whiteSpace: 'nowrap',
          }}
        >
          {formatVal(Math.min(bandMin, targetValue))}
        </Typography>
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            left: `${bandEndPct}%`,
            transform: 'translateX(-50%)',
            fontSize: 12,
            color: COLORS.textSecondary,
            fontWeight: 500,
            whiteSpace: 'nowrap',
          }}
        >
          {formatVal(Math.max(bandMin, targetValue))}
        </Typography>
      </Box>

      {/* Track + band + triangle */}
      <Box sx={{ position: 'relative', height: 8, mx: 0.5 }}>
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 8,
            borderRadius: 4,
            backgroundColor: COLORS.trackGray,
          }}
        />
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            height: 8,
            borderRadius: 4,
            backgroundColor: COLORS.accentPurple,
            left: `${bandStartPct}%`,
            width: `${Math.max(bandEndPct - bandStartPct, 0)}%`,
          }}
        />
        {/* Triangle marker */}
        <Box
          sx={{
            position: 'absolute',
            top: -10,
            left: `${currentPct}%`,
            transform: 'translateX(-50%)',
            width: 0,
            height: 0,
            borderLeft: '9px solid transparent',
            borderRight: '9px solid transparent',
            borderTop: `16px solid ${COLORS.triangle}`,
            filter: 'drop-shadow(0px 1px 1px rgba(0,0,0,0.15))',
          }}
        />
      </Box>

      {/* min / max + bold current value row */}
      <Box sx={{ position: 'relative', height: 20, mt: 0.5 }}>
        <Typography
          component="span"
          sx={{ position: 'absolute', left: 0, fontSize: 12, color: COLORS.textMuted, fontWeight: 500 }}
        >
          {formatVal(minValue)}
        </Typography>
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            left: `${currentPct}%`,
            transform: 'translateX(-50%)',
            fontSize: 13,
            color: COLORS.textPrimary,
            fontWeight: 700,
            whiteSpace: 'nowrap',
          }}
        >
          {formatVal(currentValue)}
        </Typography>
        <Typography
          component="span"
          sx={{ position: 'absolute', right: 0, fontSize: 12, color: COLORS.textMuted, fontWeight: 500 }}
        >
          {formatVal(maxValue)}
        </Typography>
      </Box>
    </Box>
  );
}
