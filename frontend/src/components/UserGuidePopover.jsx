import { Popover, Box, Typography, Divider } from '@mui/material';
import { COLORS } from '../theme/theme';

export default function UserGuidePopover({ open, anchorEl, onClose }) {
  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      slotProps={{
        paper: {
          sx: {
            width: 560,
            maxHeight: 480,
            overflowY: 'auto',
            p: 3,
            mt: 1,
            border: `1px solid ${COLORS.border}`,
            boxShadow: '0 8px 28px rgba(0,0,0,0.18)',
          },
        },
      }}
    >
      <Typography sx={{ fontSize: 13, fontWeight: 700, color: COLORS.textPrimary, mb: 0.5 }}>
        📌 Introduction:
      </Typography>
      <Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary, mb: 1.5 }}>
        This simulation leverages an interactive, traceable model that map key KPIs (or metrics) across
        different levels (L1 and L2) to establish causal relationships with tech / process interventions,
        and demonstrate how changes in operational metrics impact strategic business outcomes
      </Typography>

      <Divider sx={{ my: 1.5 }} />

      <Typography sx={{ fontSize: 13, fontWeight: 700, color: COLORS.textPrimary, mb: 0.5 }}>
        📌 Objective:
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5, mb: 1.5 }}>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Visualize interdependencies across operational metrics (Interventions → L2 → L1 → Business Outcomes)</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Analyze cascading impact of interventions on metrics and business outcomes</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Simulate baseline vs. ideal performance scenarios to estimate ROI</Typography></li>
      </Box>

      <Divider sx={{ my: 1.5 }} />

      <Typography sx={{ fontSize: 13, fontWeight: 700, color: COLORS.textPrimary, mb: 0.5 }}>
        📌 Components:
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5, mb: 1.5 }}>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Service Line Selection: Toggle buttons to view the metrics within selected service line</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Interventions: Process/Tech Interventions with a slider to input the scale of implementation across the in-scope function</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>L2 Metrics: Base metrics mapped with selected service line and L1 Metrics. Sliders to modify values and impact higher level metrics</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>L1 Metrics: Higher level metrics mapped with selected service line. Sliders to modify values and impact Business Outcomes</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Business Outcomes: End outcomes from a strategy pov. Static Sliders</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Benchmarks: Highlighted region on sliders</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Dependencies between metrics defined based on inversely / directly proportional relationships</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Calculations based on impact factor defined for the metric relationship</Typography></li>
      </Box>

      <Divider sx={{ my: 1.5 }} />

      <Typography sx={{ fontSize: 13, fontWeight: 700, color: COLORS.textPrimary, mb: 0.5 }}>
        💡 Key Assumptions:
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Benchmarks based on domain expertise and industry standards</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Metrics included are prioritized for business relevance, not exhaustive</Typography></li>
        <li><Typography sx={{ fontSize: 13.5, color: COLORS.textSecondary }}>Impact factors reflect SME input and real-world implementations; may not fully reflect mathematical dependencies</Typography></li>
      </Box>
    </Popover>
  );
}
