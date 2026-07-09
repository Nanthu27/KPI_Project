import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, TextField, Select, MenuItem, FormControl, Avatar,
} from '@mui/material';
import PostAddIcon from '@mui/icons-material/PostAdd';
import { useKpiStore } from '../store/kpiStore';
import { COLORS } from '../theme/theme';

const fieldSx = { '& .MuiOutlinedInput-root': { backgroundColor: '#F4F4F6' } };

export default function AddLobPage() {
  const navigate = useNavigate();
  const { verticalsDetailed, loadVerticalsDetailed, addLobToVertical } = useKpiStore();

  const [instanceId, setInstanceId] = useState('');
  const [lobName, setLobName] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadVerticalsDetailed();
  }, [loadVerticalsDetailed]);

  const handleSave = async () => {
    if (!instanceId || !lobName.trim()) return;
    setSaving(true);
    const ok = await addLobToVertical(instanceId, lobName.trim());
    setSaving(false);
    if (ok) navigate('/structure');
  };

  return (
    <Box sx={{ backgroundColor: COLORS.background, minHeight: '100%', pb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 3, py: 2.25, backgroundColor: '#FFFFFF', borderBottom: `1px solid ${COLORS.border}` }}>
        <Typography sx={{ fontSize: 26, fontWeight: 800, color: COLORS.textPrimary }}>
          KPI Simulator
        </Typography>
        <Avatar sx={{ width: 40, height: 40, backgroundColor: COLORS.primaryDark, fontSize: 13 }}>NG</Avatar>
      </Box>

      <Box sx={{ maxWidth: 1200, mx: 'auto', px: 3, pt: 3 }}>
        <Box sx={{ backgroundColor: '#FFFFFF', border: `1px solid ${COLORS.border}`, p: 4 }}>
          <Typography sx={{ fontSize: 18, fontWeight: 700, color: COLORS.primaryDark, mb: 3 }}>
            Instance and Line of Business (LOB) Mapping
          </Typography>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <PostAddIcon sx={{ color: COLORS.textPrimary }} />
            <Typography sx={{ fontSize: 18, fontWeight: 700, color: COLORS.textPrimary }}>
              Add LOB
            </Typography>
          </Box>
          <Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary, mb: 2.5 }}>
            Assign a new Line of Business (LOB) to the selected Vertical or Horizontal level.
          </Typography>

          <Box sx={{ border: `1px solid ${COLORS.border}`, p: 3, maxWidth: 700 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: COLORS.textPrimary, mb: 0.5 }}>
              Instance Name
            </Typography>
            <FormControl fullWidth size="small" sx={{ ...fieldSx, mb: 2.5 }}>
              <Select
                displayEmpty
                value={instanceId}
                onChange={(e) => setInstanceId(e.target.value)}
              >
                <MenuItem value=""><em>Select</em></MenuItem>
                {verticalsDetailed.map((v) => (
                  <MenuItem key={v.id} value={v.id}>{v.name}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <Typography sx={{ fontSize: 13, fontWeight: 600, color: COLORS.textPrimary, mb: 0.5 }}>
              LOB Name
            </Typography>
            <TextField
              fullWidth
              size="small"
              value={lobName}
              onChange={(e) => setLobName(e.target.value)}
              sx={fieldSx}
            />
          </Box>

          <Box sx={{ display: 'flex', gap: 2, mt: 4, maxWidth: 700 }}>
            <Button
              fullWidth
              variant="contained"
              onClick={() => navigate('/structure')}
              sx={{ backgroundColor: COLORS.primary, py: 1.4, '&:hover': { backgroundColor: COLORS.primaryDark } }}
            >
              Back
            </Button>
            <Button
              fullWidth
              variant="contained"
              onClick={handleSave}
              disabled={!instanceId || !lobName.trim() || saving}
              sx={{ backgroundColor: COLORS.primary, py: 1.4, '&:hover': { backgroundColor: COLORS.primaryDark } }}
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
