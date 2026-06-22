import { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Button, Box, FormControlLabel, Switch, Grid,
} from '@mui/material';
import { COLORS } from '../theme/theme';
import { COLUMN_KEYS } from '../store/kpiStore';

const emptyMetricForm = {
  name: '',
  unit: '%',
  min_value: 0,
  band_min: 0,
  target_value: 0,
  max_value: 100,
  default_value: 0,
  higher_is_better: false,
};

const emptyInterventionForm = {
  name: '',
  percentage: 0,
  description: '',
};

export default function CardFormDialog({ open, column, mode, record, onClose, onSubmit }) {
  const isIntervention = column === COLUMN_KEYS.INTERVENTIONS;
  const [form, setForm] = useState(isIntervention ? emptyInterventionForm : emptyMetricForm);

  useEffect(() => {
    if (mode === 'edit' && record) {
      setForm(
        isIntervention
          ? {
              name: record.name ?? '',
              percentage: record.percentage ?? 0,
              description: record.description ?? '',
            }
          : {
              name: record.name ?? '',
              unit: record.unit ?? '%',
              min_value: record.min_value ?? 0,
              band_min: record.band_min ?? 0,
              target_value: record.target_value ?? 0,
              max_value: record.max_value ?? 100,
              default_value: record.default_value ?? 0,
              higher_is_better: !!record.higher_is_better,
            }
      );
    } else {
      setForm(isIntervention ? emptyInterventionForm : emptyMetricForm);
    }
  }, [mode, record, isIntervention, open]);

  const handleChange = (field) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = () => {
    const numericFields = isIntervention
      ? ['percentage']
      : ['min_value', 'band_min', 'target_value', 'max_value', 'default_value'];
    const payload = { ...form };
    numericFields.forEach((f) => {
      payload[f] = Number(payload[f]) || 0;
    });
    onSubmit(payload);
  };

  const titlePrefix = mode === 'edit' ? 'Edit' : 'Add New';
  const titleSuffix = isIntervention ? 'Intervention' : 'KPI';

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ fontWeight: 700, color: COLORS.textPrimary }}>
        {titlePrefix} {titleSuffix}
      </DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <TextField
            label="Name"
            value={form.name}
            onChange={handleChange('name')}
            fullWidth
            size="small"
            autoFocus
          />

          {isIntervention ? (
            <>
              <TextField
                label="Description"
                value={form.description}
                onChange={handleChange('description')}
                fullWidth
                size="small"
                multiline
                minRows={2}
              />
              <TextField
                label="Percentage (0-100)"
                type="number"
                value={form.percentage}
                onChange={handleChange('percentage')}
                fullWidth
                size="small"
                inputProps={{ min: 0, max: 100 }}
              />
            </>
          ) : (
            <>
              <TextField
                label="Unit (e.g. Days, %)"
                value={form.unit}
                onChange={handleChange('unit')}
                fullWidth
                size="small"
              />
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <TextField
                    label="Min Value"
                    type="number"
                    value={form.min_value}
                    onChange={handleChange('min_value')}
                    fullWidth
                    size="small"
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    label="Max Value"
                    type="number"
                    value={form.max_value}
                    onChange={handleChange('max_value')}
                    fullWidth
                    size="small"
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    label="Target / Benchmark Value"
                    type="number"
                    value={form.target_value}
                    onChange={handleChange('target_value')}
                    fullWidth
                    size="small"
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    label="Benchmark Band Start"
                    type="number"
                    value={form.band_min}
                    onChange={handleChange('band_min')}
                    fullWidth
                    size="small"
                    helperText="Left edge of the purple zone"
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    label="Default (Baseline) Value"
                    type="number"
                    value={form.default_value}
                    onChange={handleChange('default_value')}
                    fullWidth
                    size="small"
                  />
                </Grid>
              </Grid>
              <FormControlLabel
                control={
                  <Switch
                    checked={form.higher_is_better}
                    onChange={handleChange('higher_is_better')}
                  />
                }
                label="Higher value is better"
              />
            </>
          )}
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} sx={{ color: COLORS.textSecondary }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={!form.name?.trim()}
          sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
        >
          {mode === 'edit' ? 'Save Changes' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
