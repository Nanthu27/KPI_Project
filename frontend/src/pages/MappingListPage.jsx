import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Button, IconButton, TextField,
  Select, MenuItem, FormControl, Avatar,
} from '@mui/material';
import PostAddIcon from '@mui/icons-material/PostAdd';
import AddBoxOutlinedIcon from '@mui/icons-material/AddBoxOutlined';
import ArrowCircleLeftOutlinedIcon from '@mui/icons-material/ArrowCircleLeftOutlined';
import EditIcon from '@mui/icons-material/Edit';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useKpiStore } from '../store/kpiStore';
import { COLORS } from '../theme/theme';
import ConfirmDeleteDialog from '../components/ConfirmDeleteDialog';

const fieldSx = {
  '& .MuiOutlinedInput-root': { backgroundColor: '#FFFFFF' },
};

export default function MappingListPage() {
  const navigate = useNavigate();
  const {
    verticalsDetailed, loadVerticalsDetailed,
    updateVerticalName, deleteVertical,
    updateLobName, deleteLob,
  } = useKpiStore();

  const [filterVertical, setFilterVertical] = useState('');
  const [filterLob, setFilterLob] = useState('');

  const [editingVerticalId, setEditingVerticalId] = useState(null);
  const [verticalDraft, setVerticalDraft] = useState('');
  const [editingLobId, setEditingLobId] = useState(null);
  const [lobDraft, setLobDraft] = useState('');

  const [deleteTarget, setDeleteTarget] = useState(null); // { type: 'vertical' | 'lob', id, name }

  useEffect(() => {
    loadVerticalsDetailed();
  }, [loadVerticalsDetailed]);

  // Flatten verticals + lobs into individual rows, one per Vertical/LOB pair.
  const rows = useMemo(() => {
    const out = [];
    verticalsDetailed.forEach((v) => {
      if (v.lobs && v.lobs.length) {
        v.lobs.forEach((l) => {
          out.push({ vId: v.id, vName: v.name, lobId: l.id, lobName: l.name });
        });
      } else {
        out.push({ vId: v.id, vName: v.name, lobId: null, lobName: '' });
      }
    });
    return out;
  }, [verticalsDetailed]);

  const verticalOptions = useMemo(
    () => [...new Set(verticalsDetailed.map((v) => v.name))],
    [verticalsDetailed]
  );

  const lobOptions = useMemo(() => {
    const source = filterVertical
      ? verticalsDetailed.find((v) => v.name === filterVertical)
      : null;
    const pool = source ? source.lobs : verticalsDetailed.flatMap((v) => v.lobs);
    return [...new Set(pool.map((l) => l.name))];
  }, [verticalsDetailed, filterVertical]);

  const filteredRows = rows.filter((r) => {
    if (filterVertical && r.vName !== filterVertical) return false;
    if (filterLob && r.lobName !== filterLob) return false;
    return true;
  });

  const startEditVertical = (row) => {
    setEditingVerticalId(row.vId);
    setVerticalDraft(row.vName);
  };
  const saveEditVertical = async () => {
    if (verticalDraft.trim()) {
      await updateVerticalName(editingVerticalId, verticalDraft.trim());
    }
    setEditingVerticalId(null);
  };

  const startEditLob = (row) => {
    setEditingLobId(row.lobId);
    setLobDraft(row.lobName);
  };
  const saveEditLob = async () => {
    if (lobDraft.trim()) {
      await updateLobName(editingLobId, lobDraft.trim());
    }
    setEditingLobId(null);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    if (deleteTarget.type === 'lob') {
      await deleteLob(deleteTarget.id);
    } else {
      await deleteVertical(deleteTarget.id);
    }
    setDeleteTarget(null);
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
        <Box sx={{ backgroundColor: '#FFFFFF', border: `1px solid ${COLORS.border}`, p: 3, mb: 2.5 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2.5 }}>
            <Typography sx={{ fontSize: 18, fontWeight: 700, color: COLORS.primaryDark }}>
              Instance and Line of Business (LOB) Mapping
            </Typography>
            <Button
              startIcon={<PostAddIcon />}
              onClick={() => navigate('/structure/add-lob')}
              variant="contained"
              sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
            >
              Add LOB
            </Button>
          </Box>

          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
            <Box>
              <Typography sx={{ fontSize: 13, fontWeight: 600, color: COLORS.textPrimary, mb: 0.5 }}>
                Vertical / Horizontal Level
              </Typography>
              <FormControl fullWidth size="small" sx={fieldSx}>
                <Select
                  displayEmpty
                  value={filterVertical}
                  onChange={(e) => { setFilterVertical(e.target.value); setFilterLob(''); }}
                >
                  <MenuItem value=""><em>All</em></MenuItem>
                  {verticalOptions.map((name) => (
                    <MenuItem key={name} value={name}>{name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
            <Box>
              <Typography sx={{ fontSize: 13, fontWeight: 600, color: COLORS.textPrimary, mb: 0.5 }}>
                LOB
              </Typography>
              <FormControl fullWidth size="small" sx={fieldSx}>
                <Select
                  displayEmpty
                  value={filterLob}
                  onChange={(e) => setFilterLob(e.target.value)}
                >
                  <MenuItem value=""><em>All</em></MenuItem>
                  {lobOptions.map((name) => (
                    <MenuItem key={name} value={name}>{name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
          </Box>
        </Box>

        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Button
            startIcon={<AddBoxOutlinedIcon />}
            onClick={() => navigate('/structure/new-vertical')}
            variant="contained"
            sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
          >
            Create New Vertical
          </Button>
          <Button
            startIcon={<ArrowCircleLeftOutlinedIcon />}
            onClick={() => navigate('/')}
            variant="contained"
            sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
          >
            Navigate to Simulator
          </Button>
        </Box>

        <Box sx={{ backgroundColor: '#FFFFFF', border: `1px solid ${COLORS.border}` }}>
          <Box sx={{
            display: 'grid', gridTemplateColumns: '1fr 1fr 100px',
            backgroundColor: '#D7D7DE', borderBottom: `1px solid ${COLORS.border}`,
          }}>
            {['Vertical / Horizontal Level', 'LOB', 'Delete'].map((h) => (
              <Typography key={h} sx={{ fontSize: 13.5, fontWeight: 700, color: COLORS.primaryDark, px: 2.5, py: 1.5 }}>
                {h}
              </Typography>
            ))}
          </Box>

          <Box sx={{ maxHeight: 380, overflowY: 'auto' }}>
            {filteredRows.map((row, idx) => (
              <Box
                key={`${row.vId}-${row.lobId ?? 'none'}`}
                sx={{
                  display: 'grid', gridTemplateColumns: '1fr 1fr 100px', alignItems: 'center',
                  borderBottom: idx < filteredRows.length - 1 ? `1px solid ${COLORS.border}` : 'none',
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 2.5, py: 1.5 }}>
                  {editingVerticalId === row.vId ? (
                    <TextField
                      size="small"
                      autoFocus
                      value={verticalDraft}
                      onChange={(e) => setVerticalDraft(e.target.value)}
                      onBlur={saveEditVertical}
                      onKeyDown={(e) => { if (e.key === 'Enter') saveEditVertical(); }}
                      sx={fieldSx}
                    />
                  ) : (
                    <>
                      <Typography sx={{ fontSize: 14 }}>{row.vName}</Typography>
                      <IconButton size="small" onClick={() => startEditVertical(row)}>
                        <EditIcon sx={{ fontSize: 16, color: COLORS.textMuted }} />
                      </IconButton>
                    </>
                  )}
                </Box>

                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 2.5, py: 1.5 }}>
                  {row.lobId != null && editingLobId === row.lobId ? (
                    <TextField
                      size="small"
                      autoFocus
                      value={lobDraft}
                      onChange={(e) => setLobDraft(e.target.value)}
                      onBlur={saveEditLob}
                      onKeyDown={(e) => { if (e.key === 'Enter') saveEditLob(); }}
                      sx={fieldSx}
                    />
                  ) : (
                    <>
                      <Typography sx={{ fontSize: 14 }}>{row.lobName}</Typography>
                      {row.lobId != null && (
                        <IconButton size="small" onClick={() => startEditLob(row)}>
                          <EditIcon sx={{ fontSize: 16, color: COLORS.textMuted }} />
                        </IconButton>
                      )}
                    </>
                  )}
                </Box>

                <Box sx={{ px: 2.5, py: 1.5 }}>
                  <IconButton
                    size="small"
                    onClick={() => setDeleteTarget(
                      row.lobId != null
                        ? { type: 'lob', id: row.lobId, name: row.lobName }
                        : { type: 'vertical', id: row.vId, name: row.vName }
                    )}
                  >
                    <DeleteOutlineIcon sx={{ fontSize: 18, color: COLORS.textMuted }} />
                  </IconButton>
                </Box>
              </Box>
            ))}

            {filteredRows.length === 0 && (
              <Typography sx={{ fontSize: 13, color: COLORS.textMuted, textAlign: 'center', py: 4 }}>
                No mappings found.
              </Typography>
            )}
          </Box>
        </Box>
      </Box>

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        recordName={deleteTarget?.name}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
      />
    </Box>
  );
}
