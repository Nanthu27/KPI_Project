import { Box, Typography } from '@mui/material';
import { useState, useRef, useCallback, useEffect } from 'react';
import { COLORS } from '../theme/theme';

/**
 * Custom slider visual matching the KPI Simulator screenshots exactly:
 *
 *   [low]     [band_min ▲ target_value]            [high]
 *   |----------|========purple band========|----------|
 *                  ▲ (dark triangle = current value position)
 *                       [bold current value]
 *
 * FIXES applied:
 *  1. Triangle drag now uses global pointermove/pointerup so the mouse
 *     can leave the narrow 10px track without losing the drag.
 *  2. `onChange` fires only on drag — no DB call during movement.
 *  3. `onCommit` fires once on pointerup for the caller to persist.
 */
export default function MetricSlider({
  minValue = 0,
  bandMin = 0,
  targetValue = 0,
  maxValue = 100,
  currentValue = 0,
  editable = false,
  onChange,
  onCommit,
}) {
  const trackRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  // localValue drives the triangle position while dragging; when not
  // dragging it mirrors the prop so a refresh restores saved values.
  const [localValue, setLocalValue] = useState(currentValue);

  useEffect(() => {
    if (!dragging) setLocalValue(currentValue);
  }, [currentValue, dragging]);

  const clamp = (v) => Math.min(Math.max(v, minValue), maxValue);
  const range = Math.max(maxValue - minValue, 0.0001);
  const pct = (v) => ((clamp(v) - minValue) / range) * 100;

  const displayValue = dragging ? localValue : currentValue;
  const currentPct = pct(displayValue);
  const bandStartPct = pct(Math.min(bandMin, targetValue));
  const bandEndPct = pct(Math.max(bandMin, targetValue));

  const formatVal = (v) => {
    if (v === null || v === undefined) return 0;
    // Show up to 2 decimal places, strip trailing zeros
    if (Number.isInteger(v)) return v;
    const rounded = Math.round(v * 100) / 100;
    // Remove unnecessary trailing zeros after decimal point
    return parseFloat(rounded.toFixed(2));
  };

  const valueFromClientX = useCallback(
    (clientX) => {
      const el = trackRef.current;
      if (!el) return displayValue;
      const rect = el.getBoundingClientRect();
      const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
      const raw = minValue + (maxValue - minValue) * ratio;
      return Math.round(raw * 100) / 100;
    },
    [displayValue, minValue, maxValue]
  );

  // Global pointer listeners while dragging — triangle stays grabbed
  // even if the cursor leaves the 10px track.
  useEffect(() => {
    if (!dragging) return;
    const handleMove = (e) => {
      const newVal = valueFromClientX(e.clientX);
      setLocalValue(newVal);
      onChange?.(newVal); // update parent local state only (no API)
    };
    const handleUp = (e) => {
      const finalVal = valueFromClientX(e.clientX);
      setLocalValue(finalVal);
      setDragging(false);
      onCommit?.(finalVal); // caller decides whether/when to persist
    };
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  }, [dragging, valueFromClientX, onChange, onCommit]);

  return (
    <Box sx={{ width: '100%', mt: 1.25 }}>
      {/* Band boundary callouts above the track */}
      <Box sx={{ position: 'relative', height: 22, mb: 0.5 }}>
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            left: `${Math.min(Math.max(bandStartPct, 8), 92)}%`,
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
            left: `${Math.min(Math.max(bandEndPct, 8), 92)}%`,
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
      <Box
        ref={trackRef}
        sx={{ position: 'relative', height: 10, mx: 0.5, touchAction: 'none' }}
      >
        {/* Gray base track */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 10,
            borderRadius: 999,
            backgroundColor: COLORS.trackGray,
          }}
        />
        {/* Purple benchmark band */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            height: 10,
            borderRadius: 999,
            backgroundColor: COLORS.accentPurple,
            left: `${bandStartPct}%`,
            width: `${Math.max(bandEndPct - bandStartPct, 0)}%`,
          }}
        />
        {/* Triangle handle */}
        <Box
          onPointerDown={(e) => {
            if (!editable) return;
            e.preventDefault();
            setDragging(true);
          }}
          sx={{
            position: 'absolute',
            top: -12,
            left: `${currentPct}%`,
            transform: 'translateX(-50%)',
            width: 0,
            height: 0,
            borderLeft: '9px solid transparent',
            borderRight: '9px solid transparent',
            borderTop: `16px solid ${COLORS.triangle}`,
            cursor: editable ? 'grab' : 'default',
            zIndex: 5,
            filter: 'drop-shadow(0px 1px 1px rgba(0,0,0,0.15))',
            touchAction: 'none',
          }}
        />
      </Box>

      {/* min / max + bold current value row */}
      <Box sx={{ position: 'relative', height: 24, mt: 0.9 }}>
        {/* Min label — hide when current value label is too close to left edge */}
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            left: 0,
            fontSize: 12,
            color: COLORS.textMuted,
            fontWeight: 500,
            visibility: currentPct < 18 ? 'hidden' : 'visible',
          }}
        >
          {formatVal(minValue)}
        </Typography>

        {/* Current value label — always centered on triangle position */}
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
          {formatVal(displayValue)}
        </Typography>

        {/* Max label — hide when current value label is too close to right edge */}
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            right: 0,
            fontSize: 12,
            color: COLORS.textMuted,
            fontWeight: 500,
            visibility: currentPct > 82 ? 'hidden' : 'visible',
          }}
        >
          {formatVal(maxValue)}
        </Typography>
      </Box>
    </Box>
  );
}
