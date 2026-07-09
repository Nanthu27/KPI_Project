/**
 * RecommendationCard
 * -------------------
 * Sticky summary of the most recent Goal/Advisor plan in this session —
 * the "Recommendation Card" half of the split-panel design, docked above
 * the scrolling conversation instead of a separate page/route so it works
 * inside the existing floating panel.
 *
 * Starts COLLAPSED (a small pill with a blinking icon + text: "title
 * ready — tap to view") so it doesn't open full-size and take over the
 * panel the moment a Goal/Advisor answer comes back — the user taps it
 * open when they're ready. No expand/collapse animation (per feedback,
 * it didn't look good) — it swaps instantly; the blink is what draws the
 * eye to it instead.
 *
 * Renders from `card_data`, a small structured object the backend computes
 * directly from the same tool output the chat reply is built from (see
 * backend/app/ai/cascade/agent.py::_recommendation_card_data) — never by
 * re-parsing the chat bubble's prose, which breaks the moment wording
 * changes.
 */
import { useState } from 'react';
import { Box, Typography, Chip, Button, Tooltip, IconButton } from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

const CONFIDENCE_COLOR = {
  High:   { bg: '#ECFDF5', fg: '#059669' },
  Medium: { bg: '#FFFBEB', fg: '#B45309' },
  Low:    { bg: '#FEF2F2', fg: '#DC2626' },
};

// Mount this with a `key` derived from the recommendation's identity (see
// CascadePanel: key={`${latestCard.title}-${latestCard.achieved_value}`}),
// so React remounts (and re-collapses) it fresh whenever a NEW plan replaces
// the old one.
export default function RecommendationCard({ data, onApply, disabled }) {
  const [collapsed, setCollapsed] = useState(true);

  if (!data) return null;

  const {
    kind, title, achieved_label, achieved_value, confidence, gap_pct, interventions = [],
  } = data;

  const confColor = CONFIDENCE_COLOR[confidence] || { bg: '#F3F4F6', fg: '#6B7280' };
  const isDecline = kind === 'advisor' && typeof achieved_value === 'number' && achieved_value < 0;
  const valueDisplay = typeof achieved_value === 'number'
    ? (kind === 'advisor' ? `${achieved_value > 0 ? '+' : ''}${achieved_value}%` : achieved_value)
    : '—';

  return (
    <Box sx={{
      mx: 2, mt: 1.25, mb: 0.5, borderRadius: collapsed ? '999px' : '14px',
      overflow: 'hidden', flexShrink: 0,
      border: '1px solid #E9E4FB',
      boxShadow: collapsed ? '0 2px 10px rgba(76,63,220,0.08)' : '0 2px 14px rgba(76,63,220,0.08)',
      backgroundColor: '#FFFFFF',
    }}>
      {/* Header — doubles as the compact pill when collapsed, and the
          toggle for both states. No expand/collapse animation (per
          feedback) — the collapsed pill instead blinks (icon + text) so
          it's easy to spot on its own. */}
      <Box
        onClick={() => setCollapsed(c => !c)}
        sx={{
          cursor: 'pointer',
          px: collapsed ? 1.5 : 1.75, py: collapsed ? 0.6 : 1,
          background: collapsed ? '#FFFFFF' : 'linear-gradient(135deg, #4C3FDC 0%, #7C3AED 100%)',
          display: 'flex', alignItems: 'center', gap: 1,
        }}
      >
        <Typography component="span" sx={{
          fontSize: 14, flexShrink: 0, lineHeight: 1,
          animation: collapsed ? 'cascade-pulse 1.6s ease-in-out infinite' : 'none',
        }}>
          {kind === 'goal' ? '🎯' : '⭐'}
        </Typography>
        <Typography sx={{
          fontWeight: 700, fontSize: 12, lineHeight: 1.3, minWidth: 0, flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          color: collapsed ? '#4C3FDC' : '#fff',
          animation: collapsed ? 'cascade-pulse 1.6s ease-in-out infinite' : 'none',
        }}>
          {title}{collapsed ? ' ready — tap to view' : ''}
        </Typography>
        {!collapsed && confidence && (
          <Chip label={`${confidence} confidence`} size="small" sx={{
            height: 20, fontSize: 9.5, fontWeight: 700, flexShrink: 0,
            backgroundColor: confColor.bg, color: confColor.fg,
          }} />
        )}
        <IconButton size="small" onClick={(e) => { e.stopPropagation(); setCollapsed(c => !c); }}
          sx={{ p: 0.25, color: collapsed ? '#9CA3AF' : 'rgba(255,255,255,0.85)' }}>
          {collapsed ? <ExpandMoreIcon sx={{ fontSize: 18 }} /> : <ExpandLessIcon sx={{ fontSize: 18 }} />}
        </IconButton>
      </Box>

      {!collapsed && (
        <Box sx={{ px: 1.75, py: 1.25 }}>
          {interventions.length > 0 && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.4, mb: 1 }}>
              {interventions.slice(0, 5).map((iv, i) => (
                <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography sx={{ fontSize: 12, color: '#374151' }}>{iv.name}</Typography>
                  <Typography sx={{ fontSize: 12, fontWeight: 700, color: '#4C3FDC' }}>
                    {iv.value != null ? `${iv.value}%` : '—'}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}

          <Box sx={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            pt: 0.75, borderTop: '1px dashed #E9EBF0',
          }}>
            <Typography sx={{ fontSize: 11, color: '#6B7280', fontWeight: 600 }}>
              {achieved_label}
            </Typography>
            <Typography sx={{ fontSize: 13, fontWeight: 800, color: isDecline ? '#DC2626' : '#059669' }}>
              {valueDisplay}
            </Typography>
          </Box>
          {typeof gap_pct === 'number' && (
            <Typography sx={{ fontSize: 10, color: '#9CA3AF', mt: 0.25 }}>
              Gap from target: {gap_pct.toFixed(1)}%
            </Typography>
          )}

          <Tooltip title="Moves the sliders on this page — like a manual drag, nothing is saved until you click Save on a card">
            <Button fullWidth startIcon={<CheckCircleOutlineIcon />} onClick={onApply} disabled={disabled}
              sx={{
                mt: 1.25, fontSize: 12, textTransform: 'none', fontWeight: 700, py: 0.85,
                borderRadius: '10px', color: '#fff',
                background: disabled ? '#D1D5DB' : 'linear-gradient(135deg, #6D4AE8, #4C3FDC)',
                boxShadow: disabled ? 'none' : '0 2px 10px rgba(76,63,220,0.25)',
                '&:hover': { background: disabled ? '#D1D5DB' : 'linear-gradient(135deg, #5B3AD6, #3D31C4)' },
              }}>
              Apply Plan to Sliders
            </Button>
          </Tooltip>
        </Box>
      )}
    </Box>
  );
}
