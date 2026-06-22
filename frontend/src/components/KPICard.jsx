import { Box, Paper, Typography, IconButton } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import MetricSlider from './MetricSlider';
import ImprovementIndicator from './ImprovementIndicator';
import { COLORS } from '../theme/theme';

/**
 * Shared card for Business Outcome / L1 Metric / L2 Metric.
 * Layout, top to bottom:
 *   name                                  [edit] [delete]
 *   unit
 *   [slider]
 *                                          [improvement indicator]
 */
export default function KPICard({ record, onEdit, onDelete }) {
  return (
    <Paper
      elevation={0}
      sx={{
        position: 'relative',
        borderRadius: '12px',
        backgroundColor: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        p: 1.75,
        mb: 1.5,
        boxShadow: '0 1px 3px rgba(20, 20, 43, 0.08), 0 1px 2px rgba(20,20,43,0.04)',
        transition: 'box-shadow 0.15s ease, transform 0.15s ease',
        '&:hover': {
          boxShadow: '0 6px 16px rgba(20, 20, 43, 0.14), 0 2px 4px rgba(20,20,43,0.08)',
          transform: 'translateY(-1px)',
        },
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Typography
          sx={{
            fontSize: 14.5,
            fontWeight: 600,
            color: COLORS.textPrimary,
            lineHeight: 1.3,
            pr: 1,
          }}
        >
          {record.name}
        </Typography>
        <Box sx={{ display: 'flex', gap: 0.25, flexShrink: 0 }}>
          <IconButton size="small" onClick={() => onEdit(record)} sx={{ p: 0.4 }}>
            <EditIcon sx={{ fontSize: 16, color: COLORS.textMuted }} />
          </IconButton>
          <IconButton size="small" onClick={() => onDelete(record)} sx={{ p: 0.4 }}>
            <DeleteOutlineIcon sx={{ fontSize: 17, color: COLORS.textMuted }} />
          </IconButton>
        </Box>
      </Box>

      <Typography sx={{ fontSize: 12, color: COLORS.textMuted, fontWeight: 500, mt: 0.25 }}>
        {record.unit}
      </Typography>

      <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
        <Box sx={{ flex: 1 }}>
          <MetricSlider
            minValue={record.min_value}
            bandMin={record.band_min}
            targetValue={record.target_value}
            maxValue={record.max_value}
            currentValue={record.current_value}
          />
        </Box>
        <Box sx={{ pb: 2.5 }}>
          <ImprovementIndicator
            value={record.improvement_percentage}
            higherIsBetter={record.higher_is_better}
            unit="%"
          />
        </Box>
      </Box>
    </Paper>
  );
}
