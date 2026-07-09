import { useState, useRef, useCallback, useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import { COLORS } from '../theme/theme';

/**
 * Draggable percentage slider for Intervention cards.
 *
 * FIXES applied:
 *  1. Purple fill bar now uses COLORS.accentPurple (was incorrectly
 *     set to COLORS.trackGray — invisible against the gray track).
 *  2. onChange fires during drag (local state only, no API).
 *  3. onCommit fires once on pointerup for the store to persist.
 *  4. Accepts optional minValue/maxValue props (default 0/100) purely for
 *     symmetry with MetricSlider — note the Intervention model has no
 *     per-row min_value/max_value columns (see models.py), so every real
 *     intervention's adoption slider is always the full 0-100% range.
 *     Confirmed: dragging already reaches both ends correctly; the actual
 *     gap was on the AI chat side (What-If Agent), which used to silently
 *     clamp any out-of-range value into 0-100 instead of telling the user
 *     — fixed in whatif_service.py / format_whatif_prompt instead.
 */
export default function InterventionSlider({ value = 0, minValue = 0, maxValue = 100, onChange, onCommit }) {
  const trackRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [localValue, setLocalValue] = useState(value);

  // When not dragging, sync from prop so a page refresh resets the slider.
  useEffect(() => {
    if (!dragging) setLocalValue(value);
  }, [value, dragging]);

  const clamp = useCallback((v) => Math.min(Math.max(v, minValue), maxValue), [minValue, maxValue]);
  const range = Math.max(maxValue - minValue, 0.0001);

  const valueFromClientX = useCallback((clientX) => {
    const el = trackRef.current;
    if (!el) return localValue;
    const rect = el.getBoundingClientRect();
    const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
    // Snap to whole integers — matches the integer display and the solver's output.
    return Math.round(minValue + range * ratio);
  }, [localValue, minValue, range]);

  const handlePointerDown = (e) => {
    e.preventDefault();
    setDragging(true);
    const newVal = valueFromClientX(e.clientX);
    setLocalValue(newVal);
    onChange?.(newVal);
  };

  useEffect(() => {
    if (!dragging) return;
    const handleMove = (e) => {
      const newVal = valueFromClientX(e.clientX);
      setLocalValue(newVal);
      onChange?.(newVal); // local state only
    };
    const handleUp = (e) => {
      const finalVal = valueFromClientX(e.clientX);
      setLocalValue(finalVal);
      setDragging(false);
      onCommit?.(finalVal); // persist on release
    };
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  }, [dragging, valueFromClientX, onChange, onCommit]);

  const clamped = clamp(localValue);
  const pct = ((clamped - minValue) / range) * 100;
  // Show as integer (no decimal places) — the slider snaps to whole numbers.
  const displayValue = Math.round(clamped);

  return (
    <Box sx={{ width: '100%', mt: 1 }}>
      <Box
        ref={trackRef}
        onPointerDown={handlePointerDown}
        sx={{
          position: 'relative',
          height: 8,
          mx: 0.5,
          cursor: 'pointer',
          touchAction: 'none',
        }}
      >
        {/* Gray base track */}
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
        {/* Purple fill — BUG FIX: was COLORS.trackGray (invisible) */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            height: 8,
            width: `${pct}%`,
            borderRadius: 4,
            backgroundColor: COLORS.accentPurple,
          }}
        />
        {/* Hollow circular handle */}
        <Box
          sx={{
            position: 'absolute',
            top: '50%',
            left: `${pct}%`,
            transform: 'translate(-50%, -50%)',
            width: 20,
            height: 20,
            borderRadius: '50%',
            backgroundColor: '#FFFFFF',
            border: `2px solid ${COLORS.textSecondary}`,
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            pointerEvents: 'none', // track handles all pointer events
          }}
        />
      </Box>
      <Box sx={{ position: 'relative', height: 24, mt: 0.9 }}>
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            left: 0,
            fontSize: 12,
            color: COLORS.textMuted,
            fontWeight: 500,
            visibility: pct < 10 ? 'hidden' : 'visible',
          }}
        >
          {minValue}
        </Typography>
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            left: `${pct}%`,
            transform: 'translateX(-50%)',
            fontSize: 13,
            color: COLORS.textPrimary,
            fontWeight: 700,
            whiteSpace: 'nowrap',
          }}
        >
          {displayValue}
        </Typography>
        <Typography
          component="span"
          sx={{
            position: 'absolute',
            right: 0,
            fontSize: 12,
            color: COLORS.textMuted,
            fontWeight: 500,
            visibility: pct > 85 ? 'hidden' : 'visible',
          }}
        >
          {maxValue}
        </Typography>
      </Box>
    </Box>
  );
}
