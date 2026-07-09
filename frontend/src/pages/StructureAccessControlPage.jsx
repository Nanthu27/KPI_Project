import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Tabs, Tab, TextField, Button, IconButton,
  Table, TableHead, TableBody, TableRow, TableCell, Select, MenuItem, FormControl, Avatar,
} from '@mui/material';
import HubIcon from '@mui/icons-material/Hub';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import PostAddIcon from '@mui/icons-material/PostAdd';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditIcon from '@mui/icons-material/Edit';
import { useKpiStore } from '../store/kpiStore';
import { COLORS } from '../theme/theme';

function MappingTab() {
  const navigate = useNavigate();
  const { verticalsDetailed, loadVerticalsDetailed, createVertical } = useKpiStore();
  const [verticalName, setVerticalName] = useState('');
  const [lobDraft, setLobDraft] = useState('');
  const [lobs, setLobs] = useState([]);

  useEffect(() => {
    loadVerticalsDetailed();
  }, [loadVerticalsDetailed]);

  const handleAddLob = () => {
    if (!lobDraft.trim()) return;
    setLobs((prev) => [...prev, lobDraft.trim()]);
    setLobDraft('');
  };

  const handleRemoveLobDraft = (index) => {
    setLobs((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCreate = async () => {
    if (!verticalName.trim()) return;
    const ok = await createVertical(verticalName.trim(), lobs);
    if (ok) {
      setVerticalName('');
      setLobs([]);
    }
  };

  const fieldSx = { '& .MuiOutlinedInput-root': { backgroundColor: '#F4F4F6' } };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
        <Box>
          <Typography sx={{ fontSize: 20, fontWeight: 700, color: COLORS.primary }}>
            Create New Vertical / Horizontal Level
          </Typography>
          <Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary, mt: 0.5 }}>
            Enter a name for the new simulation instance.
          </Typography>
        </Box>
        <Button
          startIcon={<HubIcon />}
          onClick={() => navigate('/structure')}
          variant="contained"
          sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
        >
          Mapping Details
        </Button>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, mt: 3 }}>
        <Box>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: COLORS.textPrimary, mb: 0.5 }}>
            Vertical/Horizontal Level
          </Typography>
          <TextField
            fullWidth
            size="small"
            value={verticalName}
            onChange={(e) => setVerticalName(e.target.value)}
            sx={fieldSx}
          />
        </Box>

        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: COLORS.textPrimary }}>LOB</Typography>
            <Button
              size="small"
              startIcon={<PostAddIcon fontSize="small" />}
              onClick={handleAddLob}
              variant="contained"
              sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
            >
              Add LOB
            </Button>
          </Box>
          <TextField
            fullWidth
            size="small"
            placeholder="Type an LOB name and click Add LOB"
            value={lobDraft}
            onChange={(e) => setLobDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAddLob(); }}
            sx={{ ...fieldSx, mb: 1 }}
          />
          <Box
            sx={{
              border: `1px solid ${COLORS.border}`,
              borderRadius: '4px',
              minHeight: 160,
              backgroundColor: '#FFFFFF',
              p: lobs.length ? 1 : 0,
            }}
          >
            {lobs.map((name, idx) => (
              <Box
                key={`${name}-${idx}`}
                sx={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  px: 1, py: 0.75, borderBottom: idx < lobs.length - 1 ? `1px solid ${COLORS.border}` : 'none',
                }}
              >
                <Typography sx={{ fontSize: 13 }}>{name}</Typography>
                <IconButton size="small" onClick={() => handleRemoveLobDraft(idx)}>
                  <DeleteOutlineIcon sx={{ fontSize: 16, color: COLORS.textMuted }} />
                </IconButton>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>

      <Box sx={{ display: 'flex', gap: 2, mt: 4 }}>
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
          onClick={handleCreate}
          disabled={!verticalName.trim()}
          sx={{ backgroundColor: COLORS.primary, py: 1.4, '&:hover': { backgroundColor: COLORS.primaryDark } }}
        >
          Create
        </Button>
      </Box>
    </Box>
  );
}

function UserOnboardingTab() {
  const navigate = useNavigate();
  const { users, roster, loadUsers, addUser, updateUser, deleteUser } = useKpiStore();
  const [selectedName, setSelectedName] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editValues, setEditValues] = useState({ name: '', email: '', role: '' });

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleAdd = async () => {
    if (!selectedName) return;
    await addUser(selectedName);
    setSelectedName('');
  };

  const startEdit = (user) => {
    setEditingId(user.id);
    setEditValues({ name: user.name, email: user.email, role: user.role });
  };

  const saveEdit = async () => {
    await updateUser(editingId, editValues);
    setEditingId(null);
  };

  const fieldSx = { '& .MuiOutlinedInput-root': { backgroundColor: '#F4F4F6' } };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography sx={{ fontSize: 20, fontWeight: 700, color: COLORS.primary }}>
          Employee Details
        </Typography>
        <Button
          startIcon={<PersonAddIcon />}
          onClick={handleAdd}
          variant="contained"
          disabled={!selectedName}
          sx={{ backgroundColor: COLORS.primary, '&:hover': { backgroundColor: COLORS.primaryDark } }}
        >
          Add User
        </Button>
      </Box>

      <Box sx={{ mb: 3, maxWidth: '50%' }}>
        <Typography sx={{ fontSize: 13, fontWeight: 600, mb: 0.5 }}>Employee Name</Typography>
        <FormControl fullWidth size="small" sx={fieldSx}>
          <Select
            value={selectedName}
            onChange={(e) => setSelectedName(e.target.value)}
            displayEmpty
          >
            <MenuItem value=""><em>Select an employee…</em></MenuItem>
            {roster
              .filter((name) => !users.some((u) => u.name === name))
              .map((name) => (
                <MenuItem key={name} value={name}>{name}</MenuItem>
              ))}
          </Select>
        </FormControl>
      </Box>

      <Table
        sx={{
          backgroundColor: '#FFFFFF',
          border: `1px solid ${COLORS.border}`,
          '& th': { backgroundColor: '#EFEFF2', fontWeight: 700, fontSize: 13.5 },
          '& td, & th': { borderBottom: `1px solid ${COLORS.border}`, fontSize: 13 },
        }}
      >
        <TableHead>
          <TableRow>
            <TableCell>Employee Name</TableCell>
            <TableCell>Email (UPN)</TableCell>
            <TableCell>Role</TableCell>
            <TableCell>Action</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {users.map((user) => (
            <TableRow key={user.id}>
              <TableCell>
                {editingId === user.id ? (
                  <TextField
                    size="small"
                    value={editValues.name}
                    onChange={(e) => setEditValues((v) => ({ ...v, name: e.target.value }))}
                    sx={fieldSx}
                  />
                ) : user.name}
              </TableCell>
              <TableCell>
                {editingId === user.id ? (
                  <TextField
                    size="small"
                    value={editValues.email}
                    onChange={(e) => setEditValues((v) => ({ ...v, email: e.target.value }))}
                    sx={fieldSx}
                  />
                ) : user.email}
              </TableCell>
              <TableCell>
                {editingId === user.id ? (
                  <TextField
                    size="small"
                    value={editValues.role}
                    onChange={(e) => setEditValues((v) => ({ ...v, role: e.target.value }))}
                    sx={fieldSx}
                  />
                ) : user.role}
              </TableCell>
              <TableCell>
                {editingId === user.id ? (
                  <Button size="small" onClick={saveEdit} sx={{ color: COLORS.primary, fontWeight: 600 }}>
                    Save
                  </Button>
                ) : (
                  <Box sx={{ display: 'flex', gap: 0.5 }}>
                    <IconButton size="small" onClick={() => startEdit(user)}>
                      <EditIcon sx={{ fontSize: 16, color: COLORS.textMuted }} />
                    </IconButton>
                    <IconButton size="small" onClick={() => deleteUser(user.id)}>
                      <DeleteOutlineIcon sx={{ fontSize: 17, color: COLORS.textMuted }} />
                    </IconButton>
                  </Box>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Box sx={{ display: 'flex', mt: 3 }}>
        <Button
          fullWidth
          variant="contained"
          onClick={() => navigate('/')}
          sx={{ backgroundColor: COLORS.primary, py: 1.4, '&:hover': { backgroundColor: COLORS.primaryDark } }}
        >
          Back
        </Button>
      </Box>
    </Box>
  );
}

export default function StructureAccessControlPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ backgroundColor: COLORS.background, minHeight: '100%', pb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 3, py: 2.25, backgroundColor: '#FFFFFF', borderBottom: `1px solid ${COLORS.border}` }}>
        <Typography sx={{ fontSize: 26, fontWeight: 800, color: COLORS.textPrimary }}>
          KPI Simulator
        </Typography>
        <Avatar sx={{ width: 40, height: 40, backgroundColor: COLORS.primaryDark, fontSize: 13 }}>NG</Avatar>
      </Box>
      <Box sx={{ maxWidth: 1200, mx: 'auto', px: 3, pt: 3 }}>
        {/* Persistent back link — always visible, regardless of active tab */}
        <Button
          onClick={() => navigate('/')}
          startIcon={<ArrowBackIcon fontSize="small" />}
          sx={{
            mb: 2, color: COLORS.textSecondary, textTransform: 'none', fontWeight: 600,
            px: 1, '&:hover': { backgroundColor: 'rgba(0,0,0,0.04)' },
          }}
        >
          Back to Simulator
        </Button>

        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{
            mb: 0,
            minHeight: 0,
            backgroundColor: '#C9C9D3',
            borderRadius: '4px 4px 0 0',
            '& .MuiTabs-indicator': { display: 'none' },
          }}
        >
          <Tab
            icon={<HubIcon fontSize="small" />}
            iconPosition="start"
            label="Mapping"
            sx={{
              minHeight: 48,
              fontWeight: 700,
              textTransform: 'none',
              backgroundColor: tab === 0 ? '#FFFFFF' : 'transparent',
              color: tab === 0 ? COLORS.primary : COLORS.textSecondary,
            }}
          />
          <Tab
            icon={<PersonAddIcon fontSize="small" />}
            iconPosition="start"
            label="User Onboarding"
            sx={{
              minHeight: 48,
              fontWeight: 700,
              textTransform: 'none',
              backgroundColor: tab === 1 ? '#FFFFFF' : 'transparent',
              color: tab === 1 ? COLORS.primary : COLORS.textSecondary,
            }}
          />
        </Tabs>

        <Box
          sx={{
            backgroundColor: '#FFFFFF',
            border: `1px solid ${COLORS.border}`,
            borderTop: 'none',
            p: 4,
          }}
        >
          {tab === 0 ? <MappingTab /> : <UserOnboardingTab />}
        </Box>
      </Box>
    </Box>
  );
}
