import { useState, useRef, useEffect } from 'react';
import {
  Box, Typography, IconButton, Tabs, Tab, TextField,
  Button, Chip, CircularProgress, InputAdornment,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SendIcon from '@mui/icons-material/Send';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import TableChartOutlinedIcon from '@mui/icons-material/TableChartOutlined';
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined';
import AccountBalanceWalletOutlinedIcon from '@mui/icons-material/AccountBalanceWalletOutlined';
import { COLORS } from '../theme/theme';
import { useAiPanelStore, AI_TABS } from '../store/aiPanelStore';
import AgentMessageBubble from './AgentMessageBubble';

const TAB_ICONS = {
  [AI_TABS.INSIGHT]: LightbulbOutlinedIcon,
  [AI_TABS.GOAL]: TrackChangesIcon,
  [AI_TABS.EXCEL]: TableChartOutlinedIcon,
  [AI_TABS.KNOWLEDGE]: MenuBookOutlinedIcon,
  [AI_TABS.DECISION]: AccountBalanceWalletOutlinedIcon,
};

const TAB_ORDER = [AI_TABS.INSIGHT, AI_TABS.GOAL, AI_TABS.EXCEL, AI_TABS.KNOWLEDGE, AI_TABS.DECISION];

export default function AiPanel({ verticalHorizontal, lob, onApplyToSliders }) {
  const {
    panelOpen, activeTab, tabs, closePanel, setActiveTab,
    getTabLabel, getSuggestedQuestions, sendMessage,
  } = useAiPanelStore();

  const [draft, setDraft] = useState('');
  const [budgetDraft, setBudgetDraft] = useState('5000');
  const scrollRef = useRef(null);

  const currentTabState = tabs[activeTab];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [currentTabState?.messages?.length, currentTabState?.loading]);

  if (!panelOpen) return null;

  const handleSend = (text) => {
    const messageText = (text ?? draft).trim();
    if (!messageText) return;
    const context = { vertical_horizontal: verticalHorizontal, lob, budget: Number(budgetDraft) || 0 };
    sendMessage(activeTab, messageText, context);
    setDraft('');
  };

  return (
    <Box
      sx={{
        width: 380,
        minWidth: 380,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#FFFFFF',
        borderLeft: `1px solid ${COLORS.border}`,
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          px: 2, py: 1.5, backgroundColor: COLORS.primary, color: '#FFFFFF',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AutoAwesomeIcon fontSize="small" />
          <Typography sx={{ fontWeight: 700, fontSize: 15 }}>AI Assistant</Typography>
        </Box>
        <IconButton size="small" onClick={closePanel} sx={{ color: '#FFFFFF' }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onChange={(_, v) => setActiveTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{
          minHeight: 44,
          backgroundColor: COLORS.panelBackground,
          '& .MuiTabs-indicator': { backgroundColor: COLORS.accentPurple, height: 3 },
        }}
      >
        {TAB_ORDER.map((tab) => {
          const Icon = TAB_ICONS[tab];
          return (
            <Tab
              key={tab}
              value={tab}
              icon={<Icon sx={{ fontSize: 17 }} />}
              iconPosition="start"
              label={getTabLabel(tab)}
              sx={{
                minHeight: 44, fontSize: 12.5, fontWeight: 600, textTransform: 'none',
                color: activeTab === tab ? COLORS.primary : COLORS.textSecondary,
              }}
            />
          );
        })}
      </Tabs>

      {/* Decision tab budget input */}
      {activeTab === AI_TABS.DECISION && (
        <Box sx={{ px: 2, py: 1, borderBottom: `1px solid ${COLORS.border}` }}>
          <TextField
            size="small"
            label="Budget (USD)"
            type="number"
            value={budgetDraft}
            onChange={(e) => setBudgetDraft(e.target.value)}
            fullWidth
            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
          />
        </Box>
      )}

      {/* Messages */}
      <Box ref={scrollRef} sx={{ flex: 1, overflowY: 'auto', px: 2, py: 2, backgroundColor: COLORS.background }}>
        {currentTabState.messages.length === 0 && (
          <Box sx={{ textAlign: 'center', mt: 4 }}>
            <Typography sx={{ fontSize: 13, color: COLORS.textMuted, mb: 1.5 }}>
              Ask the {getTabLabel(activeTab)} Agent something, or try:
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, alignItems: 'center' }}>
              {getSuggestedQuestions(activeTab).map((q, i) => (
                <Chip
                  key={i}
                  label={q}
                  onClick={() => handleSend(q)}
                  sx={{
                    backgroundColor: '#FFFFFF', border: `1px solid ${COLORS.border}`,
                    fontSize: 12.5, cursor: 'pointer', maxWidth: 300,
                    '&:hover': { backgroundColor: '#F4F2FF' },
                  }}
                />
              ))}
            </Box>
          </Box>
        )}

        {currentTabState.messages.map((m, i) => (
          <AgentMessageBubble key={i} message={m} onApplyToSliders={onApplyToSliders} />
        ))}

        {currentTabState.loading && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: 1 }}>
            <CircularProgress size={14} sx={{ color: COLORS.accentPurple }} />
            <Typography sx={{ fontSize: 12.5, color: COLORS.textMuted }}>Thinking…</Typography>
          </Box>
        )}
      </Box>

      {/* Input */}
      <Box sx={{ display: 'flex', gap: 1, p: 1.5, borderTop: `1px solid ${COLORS.border}` }}>
        <TextField
          size="small"
          fullWidth
          placeholder={`Ask the ${getTabLabel(activeTab)} Agent…`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSend(); }}
        />
        <IconButton
          onClick={() => handleSend()}
          disabled={!draft.trim() || currentTabState.loading}
          sx={{ backgroundColor: COLORS.accentPurple, color: '#FFFFFF', '&:hover': { backgroundColor: '#6644D8' } }}
        >
          <SendIcon fontSize="small" />
        </IconButton>
      </Box>
    </Box>
  );
}
