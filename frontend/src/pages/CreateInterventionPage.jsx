import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box, Typography, TextField, Button,
} from '@mui/material';
import { useKpiStore } from '../store/kpiStore';
import { interventionsApi } from '../api/client';
import { COLORS } from '../theme/theme';

export default function CreateInterventionPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const { verticalHorizontal, lob, interventions, fetchAll, showToast } = useKpiStore();

  const [values, setValues] = useState({ name: '', unit: '%', min_value: 0, max_value: 100 });

  useEffect(() => {
    if (isEdit) {
      const record = interventions.find((iv) => String(iv.id) === String(id));
      if (record) {
        setValues({
          name: record.name,
          unit: record.unit || '%',
          min_value: 0,
          max_value: 100,
        });
      }
    }
  }, [isEdit, id, interventions]);

  const handleField = (field) => (e) => setValues((prev) => ({ ...prev, [field]: e.target.value }));

  const handleSave = async () => {
    const payload = {
      name: values.name,
      vertical_horizontal: verticalHorizontal,
      lob,
    };
    try {
      if (isEdit) {
        await interventionsApi.update(id, payload);
      } else {
        await interventionsApi.create({ ...payload, percentage: 0 });
      }
      await fetchAll();
      showToast(isEdit ? 'Intervention updated' : 'Intervention created');
      navigate('/');
    } catch (e) {
      console.error(e);
      showToast('Failed to save Intervention', 'error');
    }
  };

  const fieldSx = { '& .MuiOutlinedInput-root': { backgroundColor: '#F4F4F6' } };

  return (
    <Box sx={{ backgroundColor: COLORS.background, minHeight: '100%', pb: 6 }}>
      <Box sx={{ maxWidth: 1100, mx: 'auto', px: 3, pt: 3 }}>
        <Typography sx={{ fontSize: 22, fontWeight: 700, color: COLORS.primary, mb: 1 }}>
          {isEdit ? 'Edit Intervention' : 'Create Intervention'}
        </Typography>
        <Box sx={{ height: 2, backgroundColor: COLORS.accentPurple, mb: 3, width: '100%' }} />

        <Box
          sx={{
            backgroundColor: '#FFFFFF',
            border: `1px solid ${COLORS.border}`,
            borderRadius: '6px',
            p: 3,
            mb: 4,
          }}
        >
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 3 }}>
            <TextField
              label="Intervention Name"
              value={values.name}
              onChange={handleField('name')}
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Unit"
              value={values.unit}
              onChange={handleField('unit')}
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Min Value"
              type="number"
              value={values.min_value}
              onChange={handleField('min_value')}
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Max Value"
              type="number"
              value={values.max_value}
              onChange={handleField('max_value')}
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Vertical / Horizontal Level"
              value={verticalHorizontal}
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
              InputProps={{ readOnly: true }}
            />
            <TextField
              label="Assigned To LOB"
              value={lob}
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
              InputProps={{ readOnly: true }}
            />
          </Box>
        </Box>

        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            fullWidth
            onClick={() => navigate('/')}
            variant="contained"
            sx={{ backgroundColor: COLORS.primary, py: 1.4, '&:hover': { backgroundColor: COLORS.primaryDark } }}
          >
            Back
          </Button>
          <Button
            fullWidth
            onClick={handleSave}
            variant="contained"
            disabled={!values.name?.trim()}
            sx={{ backgroundColor: COLORS.primary, py: 1.4, '&:hover': { backgroundColor: COLORS.primaryDark } }}
          >
            Save
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
