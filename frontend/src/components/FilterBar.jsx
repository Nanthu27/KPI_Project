import { Box, Typography, Select, MenuItem, Button } from '@mui/material';
import HubIcon from '@mui/icons-material/Hub';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { COLORS } from '../theme/theme';

const dropdownSx = {
  backgroundColor: '#FFFFFF',
  borderRadius: '6px',
  fontSize: 14,
  fontWeight: 500,
  color: COLORS.textPrimary,
  minWidth: 220,
  '& .MuiOutlinedInput-notchedOutline': { border: 'none' },
  '& .MuiSelect-select': { py: 1 },
};

export default function FilterBar({
  verticalHorizontal,
  lob,
  verticalOptions,
  lobOptions,
  onChangeVertical,
  onChangeLob,
  onStructureClick,
  onUserGuideClick,
  userGuideButtonRef,
}) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 2,
        px: 3,
        py: 2,
        backgroundColor: COLORS.primary,
      }}
    >
      <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
        <Box>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', mb: 0.5 }}>
            Vertical / Horizontal Level
          </Typography>
          <Select
            value={verticalHorizontal}
            onChange={(e) => onChangeVertical(e.target.value)}
            size="small"
            sx={dropdownSx}
          >
            {verticalOptions.map((v) => (
              <MenuItem key={v} value={v}>{v}</MenuItem>
            ))}
          </Select>
        </Box>

        <Box>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#FFFFFF', mb: 0.5 }}>
            LOB
          </Typography>
          <Select
            value={lob}
            onChange={(e) => onChangeLob(e.target.value)}
            size="small"
            sx={dropdownSx}
          >
            {lobOptions.map((v) => (
              <MenuItem key={v} value={v}>{v}</MenuItem>
            ))}
          </Select>
        </Box>
      </Box>

      <Box sx={{ display: 'flex', gap: 1.5 }}>
        <Button
          startIcon={<HubIcon />}
          onClick={onStructureClick}
          sx={{
            backgroundColor: COLORS.primaryDark,
            color: '#FFFFFF',
            px: 2,
            '&:hover': { backgroundColor: '#3A3950' },
          }}
        >
          Structure & Access Control
        </Button>
        <Button
          ref={userGuideButtonRef}
          endIcon={<InfoOutlinedIcon />}
          onClick={onUserGuideClick}
          sx={{
            backgroundColor: COLORS.primaryDark,
            color: '#FFFFFF',
            px: 2,
            '&:hover': { backgroundColor: '#3A3950' },
          }}
        >
          User Guide
        </Button>
      </Box>
    </Box>
  );
}
