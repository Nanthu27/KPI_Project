import { useState, useRef, useCallback, useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import { COLORS } from '../theme/theme';

/**
 * Draggable 0-100 percentage slider for Intervention cards.
 * Visual: flat gray track, purple fill up to current value, hollow
 * white circle (dark purple border) as the drag handle — matching the
 * "Intelligent Document Processing / RPA Bots / Workflow Automation"
 * sliders in the screenshot. 0 and 100 are printed at the ends, with
 * the current value printed bold beneath the handle.
 */
export default function InterventionSlider({ value = 0, onChange, onCommit }) {
  const trackRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [localValue, setLocalValue] = useState(value);

  useEffect(() => {
    if (!dragging) setLocalValue(value);
  }, [value, dragging]);

  const valueFromClientX = useCallback((clientX) => {
    const el = trackRef.current;
    if (!el) return localValue;
    const rect = el.getBoundingClientRect();
    const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
    return Math.round(ratio * 100);
  }, [localValue]);

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
      onChange?.(newVal);
    };
    const handleUp = (e) => {
      setDragging(false);
      const finalVal = valueFromClientX(e.clientX);
      onCommit?.(finalVal);
    };
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  }, [dragging, valueFromClientX, onChange, onCommit]);

  const pct = Math.min(Math.max(localValue, 0), 100);

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
            left: 0,
            height: 8,
            width: `${pct}%`,
            borderRadius: 4,
            backgroundColor: COLORS.trackGray,
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
          }}
        />
      </Box>
      <Box sx={{ position: 'relative', height: 20, mt: 0.5 }}>
        <Typography
          component="span"
          sx={{ position: 'absolute', left: 0, fontSize: 12, color: COLORS.textMuted, fontWeight: 500 }}
        >
          0
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
          {Math.round(pct)}
        </Typography>
        <Typography
          component="span"
          sx={{ position: 'absolute', right: 0, fontSize: 12, color: COLORS.textMuted, fontWeight: 500 }}
        >
          100
        </Typography>
      </Box>
    </Box>
  );
}
