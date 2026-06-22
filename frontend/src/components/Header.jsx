import { useRef } from 'react';
import { Box, Typography, Button, Avatar } from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import { COLORS } from '../theme/theme';

export default function Header({ onUploadExcel, onToggleAiPanel, aiPanelOpen }) {
  const fileInputRef = useRef(null);

  const handleButtonClick = () => fileInputRef.current?.click();

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onUploadExcel(file);
    e.target.value = '';
  };

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: 3,
        py: 2,
        backgroundColor: '#FFFFFF',
      }}
    >
      <Typography sx={{ fontSize: 26, fontWeight: 800, color: COLORS.textPrimary }}>
        KPI Simulator
      </Typography>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Button
          variant="contained"
          startIcon={<AutoAwesomeIcon fontSize="small" />}
          onClick={onToggleAiPanel}
          sx={{
            backgroundColor: aiPanelOpen ? COLORS.accentPurple : '#FFFFFF',
            color: aiPanelOpen ? '#FFFFFF' : COLORS.accentPurple,
            border: `1.5px solid ${COLORS.accentPurple}`,
            px: 2.5,
            py: 1,
            fontSize: 14,
            '&:hover': { backgroundColor: aiPanelOpen ? '#6644D8' : '#F4F2FF' },
          }}
        >
          AI Assistant
        </Button>
        <Button
          variant="contained"
          onClick={handleButtonClick}
          sx={{
            backgroundColor: COLORS.primary,
            px: 2.5,
            py: 1,
            fontSize: 14,
            '&:hover': { backgroundColor: COLORS.primaryDark },
          }}
        >
          Upload Excel
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xlsm"
          hidden
          onChange={handleFileChange}
        />
        <Avatar
          sx={{ width: 40, height: 40, backgroundColor: COLORS.primary, fontSize: 14 }}
        >
          NG
        </Avatar>
      </Box>
    </Box>
  );
}
