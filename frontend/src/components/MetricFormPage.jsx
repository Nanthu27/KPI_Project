import { useState, useEffect } from 'react';
import {
  Box, Typography, TextField, MenuItem, Select, Button,
  Table, TableHead, TableBody, TableRow, TableCell, IconButton, InputLabel, FormControl,
} from '@mui/material';
import PostAddIcon from '@mui/icons-material/PostAdd';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useNavigate } from 'react-router-dom';
import { COLORS } from '../theme/theme';

/**
 * Generic full-page Create/Edit form replicating the "Create L1 Metrics" /
 * "Create L2 Metrics" / "Create Business Outcome" / "Create Intervention"
 * screens: a core-fields panel followed (for everything except
 * Intervention) by a "Dependencies" panel where the user picks a
 * parent/child metric + impact factor, adds it to a running table, then
 * Saves everything together.
 *
 * Props:
 *  - entityLabel: "L1 Metrics" | "L2 Metrics" | "Business Outcome" | "Intervention"
 *  - nameFieldLabel: "L1 Name" | "L2 Name" | "L0 Name" | "Intervention Name"
 *  - hasDependencies: bool — Intervention has none (it's the cascade root)
 *  - dependencyLabel: "from L2 Metrics" | "from intervention" | "from L1 Metrics"
 *  - dependencyOptionLabel: "L2 Name" | "Intervention Name" | "L1 Name"
 *  - dependencyOptions: [{id, name}] — the selectable parent/child list
 *  - dependencyTableHeaders: [thisEntityColLabel, otherEntityColLabel]
 *  - initialValues / initialDependencies: for edit mode
 *  - verticalHorizontal / lob: read-only context shown in the form
 *  - onSave(values, dependencies): called when Save is clicked
 *  - onBack(): called when Back is clicked
 */
export default function MetricFormPage({
  entityLabel,
  nameFieldLabel,
  hasDependencies = true,
  dependencyLabel,
  dependencyOptionLabel,
  dependencyOptions = [],
  dependencyTableHeaders,
  initialValues,
  initialDependencies,
  verticalHorizontal,
  lob,
  onSave,
  onBack,
}) {
  const navigate = useNavigate();

  const [values, setValues] = useState({
    name: '',
    unit: '',
    default_value: '',
    min_value: '',
    max_value: '',
    band_min: '',
    target_value: '',
    metric_direction: '',
    ...initialValues,
  });

  const [dependencies, setDependencies] = useState(initialDependencies || []);
  const [pendingOptionId, setPendingOptionId] = useState('');
  const [pendingImpact, setPendingImpact] = useState('');

  useEffect(() => {
    if (initialValues) setValues((prev) => ({ ...prev, ...initialValues }));
    if (initialDependencies) setDependencies(initialDependencies);
  }, [initialValues, initialDependencies]);

  const handleField = (field) => (e) => {
    setValues((prev) => ({ ...prev, [field]: e.target.value }));
  };

  const handleAddDependency = () => {
    if (!pendingOptionId) return;
    const option = dependencyOptions.find((o) => String(o.id) === String(pendingOptionId));
    if (!option) return;
    setDependencies((prev) => [
      ...prev,
      { id: option.id, name: option.name, impact_factor: Number(pendingImpact) || 0 },
    ]);
    setPendingOptionId('');
    setPendingImpact('');
  };

  const handleRemoveDependency = (index) => {
    setDependencies((prev) => prev.filter((_, i) => i !== index));
  };

  const handleBack = () => {
    if (onBack) onBack();
    else navigate(-1);
  };

  const handleSave = () => {
    onSave(values, dependencies);
  };

  const fieldSx = {
    '& .MuiOutlinedInput-root': { backgroundColor: '#F4F4F6' },
  };

  return (
    <Box sx={{ backgroundColor: COLORS.background, minHeight: '100%', pb: 6 }}>
      <Box sx={{ maxWidth: 1100, mx: 'auto', px: 3, pt: 3 }}>
        <Typography sx={{ fontSize: 22, fontWeight: 700, color: COLORS.primary, mb: 1 }}>
          {`Create ${entityLabel}`}
        </Typography>
        <Box sx={{ height: 2, backgroundColor: COLORS.accentPurple, mb: 3, width: '100%' }} />

        {/* Core fields panel */}
        <Box
          sx={{
            backgroundColor: '#FFFFFF',
            border: `1px solid ${COLORS.border}`,
            borderRadius: '6px',
            p: 3,
            mb: 3,
          }}
        >
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 3 }}>
            <TextField
              label={nameFieldLabel}
              value={values.name}
              onChange={handleField('name')}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Unit"
              value={values.unit}
              onChange={handleField('unit')}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Default Value"
              type="number"
              value={values.default_value}
              onChange={handleField('default_value')}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Min Value"
              type="number"
              value={values.min_value}
              onChange={handleField('min_value')}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Max Value"
              type="number"
              value={values.max_value}
              onChange={handleField('max_value')}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Benchmark Min"
              type="number"
              value={values.band_min}
              onChange={handleField('band_min')}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Benchmark Max"
              type="number"
              value={values.target_value}
              onChange={handleField('target_value')}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Vertical / Horizontal Level"
              value={verticalHorizontal}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
              InputProps={{ readOnly: true }}
            />
            <TextField
              label="Assigned to LOB"
              value={lob}
              variant="outlined"
              size="small"
              sx={fieldSx}
              InputLabelProps={{ shrink: true }}
              InputProps={{ readOnly: true }}
            />
          </Box>

          <Box sx={{ mt: 3, maxWidth: '32%' }}>
            <FormControl fullWidth size="small" sx={fieldSx}>
              <InputLabel shrink>Metric Direction</InputLabel>
              <Select
                value={values.metric_direction}
                onChange={handleField('metric_direction')}
                displayEmpty
                label="Metric Direction"
              >
                <MenuItem value="">
                  <em>Find items</em>
                </MenuItem>
                <MenuItem value="higher_is_better">Higher is better</MenuItem>
                <MenuItem value="lower_is_better">Lower is better</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>

        {/* Dependencies panel */}
        {hasDependencies && (
          <>
            <Typography sx={{ fontSize: 18, fontWeight: 700, color: COLORS.primary, mb: 1 }}>
              {`Dependencies (${dependencyLabel})`}
            </Typography>
            <Box sx={{ height: 2, backgroundColor: '#C2186E', mb: 3, width: '100%' }} />

            <Box
              sx={{
                backgroundColor: '#FFFFFF',
                border: `1px solid ${COLORS.border}`,
                borderRadius: '6px',
                p: 3,
                mb: 2,
              }}
            >
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
                <FormControl fullWidth size="small" sx={fieldSx}>
                  <InputLabel shrink>{dependencyOptionLabel}</InputLabel>
                  <Select
                    value={pendingOptionId}
                    onChange={(e) => setPendingOptionId(e.target.value)}
                    displayEmpty
                    label={dependencyOptionLabel}
                  >
                    <MenuItem value="">
                      <em>Select…</em>
                    </MenuItem>
                    {dependencyOptions.map((opt) => (
                      <MenuItem key={opt.id} value={opt.id}>{opt.name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <TextField
                  label="Impact Value"
                  type="number"
                  value={pendingImpact}
                  onChange={(e) => setPendingImpact(e.target.value)}
                  variant="outlined"
                  size="small"
                  sx={fieldSx}
                  InputLabelProps={{ shrink: true }}
                />
              </Box>
            </Box>

            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
              <Button
                startIcon={<PostAddIcon />}
                onClick={handleAddDependency}
                variant="contained"
                sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
              >
                Add Dependency
              </Button>
            </Box>

            <Table
              sx={{
                backgroundColor: '#FFFFFF',
                border: `1px solid ${COLORS.border}`,
                mb: 4,
                '& th': { backgroundColor: '#D7D7DE', fontWeight: 700, color: COLORS.textPrimary, fontSize: 13.5 },
                '& td, & th': { borderBottom: `1px solid ${COLORS.border}` },
              }}
            >
              <TableHead>
                <TableRow>
                  <TableCell>{dependencyTableHeaders[0]}</TableCell>
                  <TableCell>{dependencyTableHeaders[1]}</TableCell>
                  <TableCell>Impact Factor</TableCell>
                  <TableCell>Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {dependencies.map((dep, index) => (
                  <TableRow key={`${dep.id}-${index}`}>
                    <TableCell sx={{ color: COLORS.textSecondary, fontSize: 13 }}>
                      {values.name || ''}
                    </TableCell>
                    <TableCell sx={{ color: COLORS.textSecondary, fontSize: 13 }}>{dep.name}</TableCell>
                    <TableCell sx={{ color: COLORS.textSecondary, fontSize: 13 }}>{dep.impact_factor}</TableCell>
                    <TableCell>
                      <IconButton size="small" onClick={() => handleRemoveDependency(index)}>
                        <DeleteOutlineIcon sx={{ fontSize: 18, color: COLORS.textMuted }} />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}

        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            fullWidth
            onClick={handleBack}
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
