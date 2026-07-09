import { useCallback } from 'react';
import { Box, Paper, Typography, IconButton } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import InterventionSlider from './InterventionSlider';
import { COLORS } from '../theme/theme';

export default function InterventionCard({
  record,
  onEdit,
  onDelete,
  onChangeValue,
  onCommitValue,
}) {
  const handleChange = useCallback((v) => onChangeValue?.(record.id, v), [record.id, onChangeValue]);
  const handleCommit = useCallback((v) => onCommitValue?.(record.id, v), [record.id, onCommitValue]);

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
            fontSize: 13,
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
        {record.unit || '%'}
      </Typography>

      <InterventionSlider
        value={record.percentage}
        minValue={record.min_value ?? 0}
        maxValue={record.max_value ?? 100}
        onChange={handleChange}
        onCommit={handleCommit}
      />
    </Paper>
  );
}
