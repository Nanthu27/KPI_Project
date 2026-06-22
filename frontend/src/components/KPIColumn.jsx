import { Box, Typography, IconButton, Collapse } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { COLORS } from '../theme/theme';

/**
 * One of the 4 vertical columns (Business Outcomes / L1 / L2 / Intervention).
 * - Sticky header with title + "+" add button + expand/collapse chevron.
 * - Clicking the header (or the chevron) toggles a smooth Collapse
 *   animation showing/hiding the card list below.
 * - When expanded, the body scrolls internally if content overflows the
 *   available column height.
 */
export default function KPIColumn({
  title,
  column,
  expanded,
  onToggleExpand,
  onAddClick,
  isFirstColumn = false,
  children,
}) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minWidth: 0,
        backgroundColor: isFirstColumn ? COLORS.panelBackground : 'transparent',
        borderRadius: isFirstColumn ? '12px' : 0,
        overflow: 'hidden',
      }}
    >
      <Box
        onClick={onToggleExpand}
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: isFirstColumn ? 2 : 1,
          py: 1.5,
          position: 'sticky',
          top: 0,
          zIndex: 2,
          cursor: 'pointer',
          backgroundColor: isFirstColumn ? COLORS.panelBackground : COLORS.background,
          userSelect: 'none',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <ExpandMoreIcon
            sx={{
              fontSize: 20,
              color: COLORS.textSecondary,
              transition: 'transform 0.2s ease',
              transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)',
            }}
          />
          <Typography sx={{ fontSize: 16, fontWeight: 700, color: COLORS.textPrimary }}>
            {title}
          </Typography>
        </Box>
        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            onAddClick();
          }}
          sx={{
            color: COLORS.accentPurple,
            backgroundColor: 'rgba(122, 90, 248, 0.08)',
            '&:hover': { backgroundColor: 'rgba(122, 90, 248, 0.16)' },
          }}
        >
          <AddIcon fontSize="small" />
        </IconButton>
      </Box>

      <Collapse in={expanded} timeout={250} sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <Box
          sx={{
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            px: isFirstColumn ? 2 : 1,
            pb: 2,
            '&::-webkit-scrollbar': { width: 6 },
            '&::-webkit-scrollbar-thumb': {
              backgroundColor: 'rgba(0,0,0,0.18)',
              borderRadius: 4,
            },
          }}
        >
          {children}
        </Box>
      </Collapse>
    </Box>
  );
}
