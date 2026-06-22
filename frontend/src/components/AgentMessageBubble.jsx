import { Box, Typography, Chip, Button, Table, TableBody, TableRow, TableCell, TableHead } from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import { COLORS } from '../theme/theme';
import { AI_TABS } from '../store/aiPanelStore';

function ConfidenceBadge({ score, band }) {
  const pct = Math.round((score || 0) * 100);
  const color = band === 'high' ? COLORS.accentGreen : band === 'moderate' ? '#E8A23D' : COLORS.accentRed;
  return (
    <Chip
      size="small"
      label={`Confidence: ${pct}% (${band || 'low'})`}
      sx={{
        backgroundColor: `${color}1A`,
        color,
        fontWeight: 600,
        fontSize: 12,
        height: 24,
        mt: 1,
      }}
    />
  );
}

function GoalPlanTable({ plan }) {
  if (!plan?.length) return null;
  return (
    <Table size="small" sx={{ mt: 1, backgroundColor: '#FFFFFF', border: `1px solid ${COLORS.border}` }}>
      <TableHead>
        <TableRow sx={{ backgroundColor: '#EFEFF2' }}>
          <TableCell sx={{ fontWeight: 700, fontSize: 12.5 }}>Intervention</TableCell>
          <TableCell sx={{ fontWeight: 700, fontSize: 12.5 }} align="right">Recommended</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {plan.map((item, i) => (
          <TableRow key={i}>
            <TableCell sx={{ fontSize: 13 }}>{item.intervention}</TableCell>
            <TableCell sx={{ fontSize: 13, fontWeight: 600 }} align="right">{item.recommended_value}%</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ExcelTraceSteps({ steps }) {
  if (!steps?.length) return null;
  return (
    <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
      {steps.map((s, i) => (
        <Box
          key={i}
          sx={{
            backgroundColor: '#FFFFFF', border: `1px solid ${COLORS.border}`,
            borderRadius: 1, p: 1, fontSize: 12.5,
          }}
        >
          <Typography sx={{ fontSize: 11, fontWeight: 700, color: COLORS.accentPurple }}>STEP {s.step}</Typography>
          <Typography sx={{ fontSize: 13 }}>{s.description}</Typography>
          <Typography sx={{ fontSize: 12, color: COLORS.textSecondary, fontFamily: 'monospace' }}>{s.formula}</Typography>
        </Box>
      ))}
    </Box>
  );
}

function KnowledgeSources({ sources }) {
  if (!sources?.length) return null;
  return (
    <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
      {sources.map((s, i) => (
        <Chip key={i} size="small" label={s.ref} sx={{ fontSize: 11, backgroundColor: '#EFEFF2' }} />
      ))}
    </Box>
  );
}

function DecisionOptions({ options }) {
  if (!options?.length) return null;
  return (
    <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
      {options.map((opt, i) => (
        <Box key={i} sx={{ backgroundColor: '#FFFFFF', border: `1px solid ${COLORS.border}`, borderRadius: 1, p: 1.25 }}>
          <Typography sx={{ fontSize: 13, fontWeight: 700 }}>{opt.label}</Typography>
          <Box sx={{ display: 'flex', gap: 2, mt: 0.5, flexWrap: 'wrap' }}>
            <Typography sx={{ fontSize: 12, color: COLORS.textSecondary }}>Cost: ${opt.total_cost?.toLocaleString()}</Typography>
            <Typography sx={{ fontSize: 12, color: COLORS.textSecondary }}>ROI: {opt.roi_pct}%</Typography>
            <Typography sx={{ fontSize: 12, color: COLORS.textSecondary }}>Payback: {opt.payback_months}mo</Typography>
          </Box>
        </Box>
      ))}
    </Box>
  );
}

export default function AgentMessageBubble({ message, onApplyToSliders }) {
  if (message.role === 'user') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1.5 }}>
        <Box
          sx={{
            backgroundColor: COLORS.primary, color: '#FFFFFF',
            borderRadius: '12px 12px 2px 12px', px: 1.5, py: 1, maxWidth: '85%',
          }}
        >
          <Typography sx={{ fontSize: 13.5 }}>{message.text}</Typography>
        </Box>
      </Box>
    );
  }

  const { tab, data } = message;
  const showApply = data.action_available === 'apply_to_sliders' && !data._error;

  return (
    <Box sx={{ display: 'flex', justifyContent: 'flex-start', mb: 1.5 }}>
      <Box
        sx={{
          backgroundColor: data._error ? '#FCEAEA' : '#FFFFFF',
          border: `1px solid ${data._error ? COLORS.accentRed : COLORS.border}`,
          borderRadius: '2px 12px 12px 12px', px: 1.5, py: 1.25, maxWidth: '92%',
        }}
      >
        <Typography sx={{ fontSize: 13.5, whiteSpace: 'pre-wrap', color: COLORS.textPrimary }}>
          {data.response_text}
        </Typography>

        {tab === AI_TABS.GOAL && <GoalPlanTable plan={data.plan} />}
        {tab === AI_TABS.GOAL && data.confidence_score !== undefined && (
          <ConfidenceBadge score={data.confidence_score} band={data.confidence_band} />
        )}
        {tab === AI_TABS.EXCEL && <ExcelTraceSteps steps={data.trace_steps} />}
        {tab === AI_TABS.EXCEL && data.source_citation && (
          <Typography sx={{ fontSize: 11, color: COLORS.textMuted, mt: 0.75 }}>
            Source: {data.source_citation}
          </Typography>
        )}
        {tab === AI_TABS.KNOWLEDGE && <KnowledgeSources sources={data.sources} />}
        {tab === AI_TABS.DECISION && <DecisionOptions options={data.all_options} />}

        {showApply && (
          <Button
            size="small"
            startIcon={<CheckCircleOutlineIcon fontSize="small" />}
            onClick={() => onApplyToSliders(data)}
            sx={{
              mt: 1, fontSize: 12, fontWeight: 600, textTransform: 'none',
              backgroundColor: COLORS.accentPurple, color: '#FFFFFF',
              '&:hover': { backgroundColor: '#6644D8' },
            }}
            variant="contained"
          >
            Apply to Sliders
          </Button>
        )}
      </Box>
    </Box>
  );
}
