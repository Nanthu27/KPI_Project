/**
 * CascadeButton
 * Floating Action Button that toggles the Cascade panel.
 * Placed in App.jsx alongside existing layout — no existing code modified.
 */
import { Box, Fab, Tooltip, Badge } from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import { useCascadeStore } from '../store/cascadeStore';

export default function CascadeButton() {
  const { isOpen, togglePanel, messages, isStreaming } = useCascadeStore();

  const unread = messages.filter((m) => m.role === 'assistant' && !m.seen).length;

  // The panel has its own ✕ in the header once open — this FAB's only job
  // is opening it. Keeping it visible (and separately positioned) while
  // open was what caused it to end up overlapping the panel's own voice/
  // text input row.
  if (isOpen) return null;

  return (
    <Tooltip title="Open Cascade AI" placement="right">
      <Box
        className="cascade-fab"
        sx={{
          position: 'fixed',
          bottom: 28,
          right: 24,
          zIndex: 1400,
        }}
      >
        <Badge badgeContent={isStreaming ? '...' : 0} color="secondary">
          <Fab
            onClick={togglePanel}
            sx={{
              background: isOpen
                ? 'linear-gradient(135deg, #545379 0%, #3D3C5E 100%)'
                : 'linear-gradient(135deg, #7A5AF8 0%, #545379 100%)',
              color: '#fff',
              width: 52,
              height: 52,
              boxShadow: '0 4px 20px rgba(122, 90, 248, 0.45)',
              '&:hover': {
                background: 'linear-gradient(135deg, #6D4AE8 0%, #484769 100%)',
                transform: 'scale(1.08)',
              },
              transition: 'all 0.2s ease',
            }}
          >
            <AutoAwesomeIcon sx={{ fontSize: 22 }} />
          </Fab>
        </Badge>
      </Box>
    </Tooltip>
  );
}
