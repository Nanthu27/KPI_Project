import { Box, Typography, IconButton } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { COLORS } from '../theme/theme';

/**
 * One of the 4 vertical columns (Business Outcomes / L1 / L2 / Intervention).
 * - Static header with title + "+" add button.
 * - Expand/collapse chevron removed per request — column body is always visible.
 * - Body scrolls internally if content overflows the available column height.
 */
export default function KPIColumn({
  title,
  column,
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
        minHeight: 0,
        backgroundColor: isFirstColumn ? COLORS.panelBackground : COLORS.card,
        borderRadius: '12px',
        border: isFirstColumn ? 'none' : `1px solid ${COLORS.border}`,
        overflow: 'hidden',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: isFirstColumn ? 2 : 1,
          py: 1.5,
          position: 'sticky',
          top: 0,
          zIndex: 2,
          backgroundColor: isFirstColumn ? COLORS.panelBackground : COLORS.card,
          userSelect: 'none',
          borderBottom: isFirstColumn ? 'none' : `1px solid ${COLORS.border}`,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Typography sx={{ fontSize: 16, fontWeight: 700, color: isFirstColumn ? '#FFFFFF' : COLORS.textPrimary }}>
            {title}
          </Typography>
        </Box>
        <IconButton
          size="small"
          onClick={onAddClick}
          sx={{
            color: isFirstColumn ? '#FFFFFF' : COLORS.accentPurple,
            backgroundColor: 'rgba(122, 90, 248, 0.08)',
            '&:hover': { backgroundColor: 'rgba(122, 90, 248, 0.16)' },
          }}
        >
          <AddIcon fontSize="small" />
        </IconButton>
      </Box>

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
          px: isFirstColumn ? 2 : 1.25,
          py: 1,
          scrollbarWidth: 'thin',

          '&::-webkit-scrollbar': {
            width: '8px',
          },

          '&::-webkit-scrollbar-track': {
            background: '#E5E5E5',
            borderRadius: '10px',
          },

          '&::-webkit-scrollbar-thumb': {
            background: '#8A8A8A',
            borderRadius: '10px',
          },

          '&::-webkit-scrollbar-thumb:hover': {
            background: '#6E6E6E',
          },
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
