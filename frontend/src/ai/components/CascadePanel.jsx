/**
 * CascadePanel — Production UI
 * 
 * Improvements:
 *  - Cleaner chat bubbles with intent badge on every AI message
 *  - Structured AI answers: numbered steps, tables, color-coded metrics  
 *  - Thinking animation shows which agent is active
 *  - Dynamic starters from live metric names (never hardcoded)
 *  - Apply button shows real intervention values before applying
 *  - Voice input ready (Web Speech API)
 *  - Collapsible tool-info row
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import {
  Box, Drawer, Typography, IconButton, TextField, CircularProgress,
  Chip, Tooltip, Paper, Button, Divider, Collapse, Avatar,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SendIcon from '@mui/icons-material/Send';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import RefreshIcon from '@mui/icons-material/Refresh';
import MicIcon from '@mui/icons-material/Mic';
import MicOffIcon from '@mui/icons-material/MicOff';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useCascadeStore } from '../store/cascadeStore';
import ProgressiveMarkdownRenderer from './ProgressiveMarkdownRenderer';
import RecommendationCard from './RecommendationCard';

const DRAWER_WIDTH = 520;

// ── Intent metadata ──────────────────────────────────────────────────────────
const INTENT = {
  insight:   { icon: '💡', label: 'Insight Agent',   subtitle: 'Explains what changed on this page and why', color: '#4338CA', bg: '#EEF2FF', thinking: 'Reading your live simulation data…' },
  goal:      { icon: '🎯', label: 'Goal Agent',       subtitle: 'Finds the slider values that hit your target', color: '#059669', bg: '#ECFDF5', thinking: 'Running reverse solver on your KPIs…' },
  knowledge: { icon: '📚', label: 'Knowledge Agent',  subtitle: 'Searches your KPI definitions & docs', color: '#B45309', bg: '#FFFBEB', thinking: 'Searching knowledge base…' },
  trace:     { icon: '🔍', label: 'Trace Agent',      subtitle: 'Formula path through the metric hierarchy', color: '#0369A1', bg: '#F0F9FF', thinking: 'Tracing formula path through hierarchy…' },
  advisor:   { icon: '⭐', label: 'Decision Advisor', subtitle: 'Ranks strategies by measured impact', color: '#7C3AED', bg: '#FAF5FF', thinking: 'Testing intervention strategies…' },
  error:     { icon: '⚠️', label: 'Error',            subtitle: '', color: '#DC2626', bg: '#FEF2F2', thinking: '' },
};

// ── Animated dots ─────────────────────────────────────────────────────────────
function ThinkingDots() {
  return (
    <Box sx={{ display: 'flex', gap: '3px', alignItems: 'center', height: 16 }}>
      {[0, 1, 2].map(i => (
        <Box key={i} sx={{
          width: 6, height: 6, borderRadius: '50%', backgroundColor: '#9CA3AF',
          animation: 'cascade-bounce 1.2s ease-in-out infinite',
          animationDelay: `${i * 0.2}s`,
        }} />
      ))}
    </Box>
  );
}

// ── Agent Activity timeline — which agents have actually contributed in
// this session so far, dimmed for the ones that haven't been called yet.
// Built from the real `intent` on each assistant message (set from the
// backend's deterministic router, not guessed client-side). Always shown
// (even before any agent has replied) with a short label per icon, so all
// five agents read as distinct, separately-identifiable items rather than
// a row of near-identical small icons.
const SHORT_LABEL = {
  insight: 'Insight', goal: 'Goal', knowledge: 'Knowledge',
  trace: 'Trace', advisor: 'Advisor',
};
function AgentActivityRow({ usedIntents }) {
  const items = Object.entries(INTENT).filter(([key]) => key !== 'error');
  return (
    <Box sx={{
      px: 2, py: 0.6, backgroundColor: '#FFFFFF', borderBottom: '1px solid #E9EBF0',
      display: 'flex', alignItems: 'center', gap: 0.7, flexWrap: 'wrap',
    }}>
      <Typography sx={{ fontSize: 9.5, color: '#9CA3AF', fontWeight: 700, mr: 0.25 }}>
        AGENT ACTIVITY
      </Typography>
      {items.map(([key, m]) => {
        const used = usedIntents.has(key);
        return (
          <Tooltip key={key} title={used ? `${m.label} contributed to this session` : `${m.label} — not used yet`}>
            <Box sx={{
              display: 'flex', alignItems: 'center', gap: 0.35, px: 0.7, py: 0.2,
              borderRadius: '6px', backgroundColor: used ? m.bg : '#F9FAFB',
              border: `1px solid ${used ? m.color + '33' : '#E9EBF0'}`,
              opacity: used ? 1 : 0.55,
            }}>
              <Box sx={{
                width: 5, height: 5, borderRadius: '50%',
                backgroundColor: used ? '#34D399' : '#D1D5DB',
              }} />
              <Typography sx={{ fontSize: 10.5 }}>{m.icon}</Typography>
              <Typography sx={{ fontSize: 9.5, fontWeight: 600, color: used ? m.color : '#9CA3AF' }}>
                {SHORT_LABEL[key]}
              </Typography>
            </Box>
          </Tooltip>
        );
      })}
    </Box>
  );
}

// ── Single message bubble ─────────────────────────────────────────────────────
function Bubble({ msg, isLast, isStreaming, onFollowup, onCopy }) {
  const isUser = msg.role === 'user';
  const meta = INTENT[msg.intent] || null;
  const isWaiting = isStreaming && isLast && !isUser && !msg.content;
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (isWaiting) {
    const thinkingMeta = INTENT[msg.intent || 'knowledge'];
    return (
      <Box sx={{ mb: 2, maxWidth: '90%' }}>
        {thinkingMeta && (
          <Box sx={{
            background: 'linear-gradient(135deg, #362F5C 0%, #423A6E 100%)',
            borderRadius: '12px 12px 0 0', px: 2, py: 1,
            display: 'flex', alignItems: 'center', gap: 1,
          }}>
            <Box sx={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: '#34D399', flexShrink: 0 }} />
            <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: 12.5 }}>
              {thinkingMeta.icon} {thinkingMeta.label}
            </Typography>
          </Box>
        )}
        <Paper elevation={0} sx={{
          px: 2, py: 1.5, borderRadius: thinkingMeta ? '0 0 12px 12px' : '4px 16px 16px 16px',
          backgroundColor: '#F9FAFB', border: '1px solid #E5E7EB', borderTop: thinkingMeta ? 'none' : '1px solid #E5E7EB',
        }}>
          <Typography sx={{ fontSize: 12, color: '#6B7280', mb: 0.75 }}>
            {thinkingMeta?.thinking || 'Thinking…'}
          </Typography>
          <ThinkingDots />
        </Paper>
      </Box>
    );
  }

  return (
    <Box sx={{ mb: 2, display: 'flex', flexDirection: 'column',
               alignItems: isUser ? 'flex-end' : 'flex-start' }}>

      {/* Agent header bar — dark gradient bar with status dot, agent name,
          and a one-line subtitle, styled after the reference design decks.
          This sits flush against the card body below (no gap) so the two
          read as a single agent-response card, not a chat bubble. */}
      {!isUser && meta && msg.content && (
        <Box sx={{
          width: '97%',
          background: 'linear-gradient(135deg, #362F5C 0%, #423A6E 100%)',
          borderRadius: '12px 12px 0 0',
          px: 2, py: 1,
          display: 'flex', alignItems: 'center', gap: 1,
        }}>
          <Box sx={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: '#34D399', flexShrink: 0 }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: 12.5, lineHeight: 1.35 }}>
              {meta.icon} {meta.label}
            </Typography>
            {meta.subtitle && (
              <Typography sx={{ color: 'rgba(255,255,255,0.62)', fontSize: 10.5, lineHeight: 1.3 }}>
                {meta.subtitle}
              </Typography>
            )}
          </Box>
        </Box>
      )}

      {/* Card body */}
      <Box sx={{
        maxWidth: isUser ? '80%' : '97%',
        width: !isUser ? '97%' : undefined,
        px: 2, py: isUser ? 1 : 1.4,
        borderRadius: isUser ? '16px 16px 4px 16px' : (meta && msg.content ? '0 0 12px 12px' : '12px'),
        background: isUser
          ? 'linear-gradient(135deg, #4C3FDC 0%, #6D4AE8 100%)'
          : '#FBFAFF',
        color: isUser ? '#fff' : '#1F2937',
        boxShadow: isUser
          ? '0 4px 12px rgba(76,63,220,0.3)'
          : '0 1px 6px rgba(0,0,0,0.05)',
        border: isUser ? 'none' : '1px solid #E9E4FB',
        borderTop: (!isUser && meta && msg.content) ? 'none' : (isUser ? 'none' : '1px solid #E9E4FB'),
        position: 'relative',
      }}>
        {isUser
          ? <Typography sx={{ fontSize: 13.5, lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>
              {msg.content}
            </Typography>
          : <ProgressiveMarkdownRenderer content={msg.content || ''} isStreaming={isStreaming && isLast} />
        }
      </Box>

      {/* Actions row (AI messages only) */}
      {!isUser && msg.content && (
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, ml: 0.5, alignItems: 'center' }}>
          <Tooltip title={copied ? 'Copied!' : 'Copy response'}>
            <IconButton size="small" onClick={handleCopy}
              sx={{ p: 0.4, color: copied ? '#059669' : '#9CA3AF',
                    '&:hover': { color: '#4C3FDC', backgroundColor: '#EEF2FF' } }}>
              <ContentCopyIcon sx={{ fontSize: 13 }} />
            </IconButton>
          </Tooltip>
          <Tooltip title="Helpful">
            <IconButton size="small"
              sx={{ p: 0.4, color: '#9CA3AF', '&:hover': { color: '#059669', backgroundColor: '#ECFDF5' } }}>
              <ThumbUpAltOutlinedIcon sx={{ fontSize: 13 }} />
            </IconButton>
          </Tooltip>
        </Box>
      )}

      {/* The old per-bubble "Apply Top Recommendation to Sliders" button
          used to render here for advisor responses. Removed: the sticky
          Recommendation Card above the conversation is now the ONE apply
          action for both Goal and Advisor plans. Having two buttons that
          both applied "the top recommendation" (sometimes to slightly
          different things) made it easy to click both and get two
          back-to-back confirmation bubbles for the same action. */}

      {/* Dynamic follow-up chips */}
      {!isUser && isLast && !isStreaming && msg.followups?.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mt: 1, maxWidth: '100%' }}>
          {msg.followups.map((q, i) => (
            <Chip key={i} label={q} size="small" onClick={() => onFollowup(q)}
              sx={{ fontSize: 11, cursor: 'pointer', height: 26, fontWeight: 500,
                    backgroundColor: '#F3F0FF', color: '#5B21B6', border: '1px solid #DDD6FE',
                    '&:hover': { backgroundColor: '#EDE9FE', borderColor: '#7C3AED' },
                    transition: 'all 0.15s' }} />
          ))}
        </Box>
      )}
    </Box>
  );
}

// ── Empty state with dynamic starters ────────────────────────────────────────
function EmptyState({ starters, onStart, isStreaming }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
               pt: 2.5, pb: 1, gap: 1.5 }}>
      <Box sx={{
        width: 56, height: 56, borderRadius: '50%',
        background: 'linear-gradient(135deg, #4C3FDC 0%, #7C3AED 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 6px 20px rgba(76,63,220,0.35)',
      }}>
        <AutoAwesomeIcon sx={{ color: '#fff', fontSize: 28 }} />
      </Box>

      <Box sx={{ textAlign: 'center' }}>
        <Typography sx={{ fontSize: 15, fontWeight: 700, color: '#1E1B4B', mb: 0.4 }}>
          Cascade AI
        </Typography>
        <Typography sx={{ fontSize: 12.5, color: '#6B7280', lineHeight: 1.6, maxWidth: 300 }}>
          Ask anything about your live KPI data.<br/>
          I read your actual metrics — not generic examples.
        </Typography>
      </Box>

      {/* Agent capability pills */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, justifyContent: 'center', maxWidth: 340 }}>
        {Object.values(INTENT).filter(m => m.label !== 'Error').map(m => (
          <Chip key={m.label}
            icon={<span style={{ fontSize: 11, marginLeft: 4 }}>{m.icon}</span>}
            label={m.label} size="small"
            sx={{ fontSize: 10, height: 22, fontWeight: 600,
                  backgroundColor: m.bg, color: m.color }} />
        ))}
      </Box>

      <Divider sx={{ width: '100%', my: 0.5 }}>
        <Typography sx={{ fontSize: 10, color: '#9CA3AF', fontWeight: 500 }}>
          Try asking
        </Typography>
      </Divider>

      <Box sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 0.75 }}>
        {starters.map((s) => (
          <Paper key={s.label} elevation={0} onClick={() => !isStreaming && onStart(s.message, s.intent)}
            sx={{
              px: 1.75, py: 1.1, cursor: isStreaming ? 'not-allowed' : 'pointer',
              borderRadius: '10px', border: '1px solid #E9EBF0',
              backgroundColor: isStreaming ? '#F9FAFB' : '#FFFFFF',
              display: 'flex', alignItems: 'center', gap: 1,
              '&:hover': !isStreaming ? {
                backgroundColor: '#F3F0FF', borderColor: '#7C3AED',
                transform: 'translateX(3px)',
              } : {},
              transition: 'all 0.15s',
            }}>
            <Typography sx={{ fontSize: 14 }}>{s.emoji || '💬'}</Typography>
            <Typography sx={{ fontSize: 12.5, color: '#374151', lineHeight: 1.4, fontWeight: 500 }}>
              {s.label}
            </Typography>
          </Paper>
        ))}
      </Box>
    </Box>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────────────
export default function CascadePanel({ onApplyToSliders, pageContext }) {
  const {
    isOpen, closePanel,
    messages, isStreaming, starters, clearMessages,
    sendMessage, applyRecommendation, applyRecommendationToMessage, updateStarters,
  } = useCascadeStore();

  const [input, setInput] = useState('');
  const [listening, setListening] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

  // Update dynamic starters when page data changes
  useEffect(() => { updateStarters(pageContext); }, [pageContext, updateStarters]);

  // Reset the conversation whenever the user switches Vertical/LOB. Without
  // this, switching from e.g. "Operations / Revenue Growth" to "Finance &
  // Accounting / Cash Conversion Cycle" kept the OLD conversation (and its
  // sticky Recommendation Card) sitting in the store. The card's cardData
  // is just whatever the last Goal/Advisor message produced, from whatever
  // page that was — so on the new page it could show a totally different
  // vertical's metric and intervention names as if they applied here. This
  // is what "why is it answering about Revenue Growth when I'm on Cash
  // Conversion Cycle" actually was: stale front-end state, not the backend
  // mixing verticals (the backend calls are correctly scoped per request).
  const prevScopeRef = useRef(null);
  useEffect(() => {
    const scope = `${pageContext?.filters?.vertical || ''}::${pageContext?.filters?.lob || ''}`;
    if (prevScopeRef.current !== null && prevScopeRef.current !== scope && messages.length > 0) {
      clearMessages();
      appliedCountRef.current = 0;
    }
    prevScopeRef.current = scope;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageContext?.filters?.vertical, pageContext?.filters?.lob]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 200);
  }, [isOpen]);

  // Close on click outside: fires when the user clicks anywhere that is
  // not inside the drawer panel or the FAB that opens it.
  useEffect(() => {
    if (!isOpen) return;
    const onDown = (e) => {
      const panel = document.querySelector('[data-cascade-panel="true"]');
      const fab   = document.querySelector('.cascade-fab');
      if (panel?.contains(e.target)) return;
      if (fab?.contains(e.target))   return;
      closePanel();
    };
    // 200 ms grace period so the FAB click that opened the panel doesn't
    // immediately re-close it via this same listener.
    const t = setTimeout(() => document.addEventListener('mousedown', onDown, true), 200);
    return () => {
      clearTimeout(t);
      document.removeEventListener('mousedown', onDown, true);
    };
  }, [isOpen, closePanel]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    sendMessage(text, null, pageContext);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  // Voice input via Web Speech API
  const handleVoice = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert('Voice input not supported in this browser. Try Chrome.'); return; }

    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = false;
    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      setInput(prev => prev + (prev ? ' ' : '') + transcript);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.start();
    recognitionRef.current = rec;
    setListening(true);
  }, [listening]);

  // NOTE: the old handleApply() (sent "Apply the top recommendation to my
  // sliders" as a chat message) was removed along with its button — see
  // the comment in Bubble() above. handleApplyCard() below is now the one
  // apply path, used directly by the sticky Recommendation Card.

  // Auto-apply as soon as a message arrives carrying a deterministic
  // apply_action (Advisor Mode 2). Tracks how many messages have already
  // been checked so we never re-apply the same action twice.
  const appliedCountRef = useRef(0);
  useEffect(() => {
    if (isStreaming) return;
    for (let i = appliedCountRef.current; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role === 'assistant' && msg.applyAction?.sliders) {
        const ivs = Object.entries(msg.applyAction.sliders).map(([name, value]) => ({ name, value }));
        applyRecommendationToMessage(i, ivs, onApplyToSliders);
      }
    }
    appliedCountRef.current = messages.length;
  }, [messages, isStreaming, applyRecommendationToMessage, onApplyToSliders]);

  // Active interventions for live bar — only those with percentage > 0
  const activeIVs = (pageContext?.activeInterventions || []).filter(iv => (iv.percentage || 0) > 0);
  const boCount = pageContext?.businessOutcomes?.length || 0;
  const isLive = activeIVs.length > 0;

  const isEmpty = messages.length === 0;
  const lastMsg = messages[messages.length - 1];
  const isWaitingFirst = isStreaming && lastMsg?.role === 'assistant' && !lastMsg?.content;

  // Which agents have contributed to this session, for the activity row.
  const usedIntents = new Set(
    messages.filter(m => m.role === 'assistant' && m.intent && m.intent !== 'error').map(m => m.intent)
  );
  // The Recommendation Card only shows while its message is still the most
  // recent thing in the conversation. As soon as the user asks a follow-up
  // question — even before the next answer streams back — it disappears,
  // instead of sticking around indefinitely from an old turn.
  const lastMessage = messages[messages.length - 1];
  const latestCard = (lastMessage?.role === 'assistant' && lastMessage?.cardData) || null;
  const panelWidth = latestCard ? DRAWER_WIDTH + 60 : DRAWER_WIDTH;

  // Direct, local apply for the sticky Recommendation Card. Unlike
  // handleApply() above (which sends a chat message that only ever
  // triggers the Advisor's apply-mode), this uses the exact intervention
  // values already computed and cached in card_data — correct for a GOAL
  // card too, and doesn't need a round-trip to the LLM just to apply
  // numbers we already have.
  const handleApplyCard = () => {
    if (!latestCard?.interventions?.length) return;
    applyRecommendation(latestCard.interventions, onApplyToSliders);
  };

  return (
    <>
      <style>{`
        @keyframes cascade-bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-6px); }
        }
        .cascade-messages { scroll-behavior: smooth; }
        .cascade-messages::-webkit-scrollbar { width: 3px; }
        .cascade-messages::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
      `}</style>

      <Drawer anchor="right" open={isOpen} onClose={closePanel} variant="persistent"
        PaperProps={{ 'data-cascade-panel': 'true', sx: {
          width: panelWidth, display: 'flex', flexDirection: 'column',
          borderLeft: 'none', transition: 'width 0.2s ease',
          boxShadow: '-8px 0 40px rgba(0,0,0,0.12)',
          backgroundColor: '#F8F9FF',
        }}}>

        {/* ── Header ── */}
        <Box sx={{
          px: 2, py: 1.5,
          background: 'linear-gradient(135deg, #2D2B55 0%, #3D3C7E 50%, #4C3FDC 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
            <Box sx={{
              width: 32, height: 32, borderRadius: '10px',
              background: 'rgba(255,255,255,0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              backdropFilter: 'blur(4px)',
            }}>
              <AutoAwesomeIcon sx={{ color: '#C4B5FD', fontSize: 18 }} />
            </Box>
            <Box>
              <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: 14, lineHeight: 1.2 }}>
                Cascade AI
              </Typography>
              <Typography sx={{ color: 'rgba(255,255,255,0.6)', fontSize: 10, lineHeight: 1.2 }}>
                Powered by Google Gemini · Flash
              </Typography>
            </Box>
            <Chip label="AI" size="small" sx={{
              height: 18, fontSize: 9, fontWeight: 900,
              backgroundColor: '#7C3AED', color: '#fff', ml: 0.5,
            }} />
          </Box>

          <Box sx={{ display: 'flex', gap: 0.25 }}>
            <Tooltip title="Clear conversation">
              <IconButton size="small" onClick={clearMessages}
                sx={{ color: 'rgba(255,255,255,0.6)', '&:hover': { color: '#fff', backgroundColor: 'rgba(255,255,255,0.1)' } }}>
                <RefreshIcon sx={{ fontSize: 17 }} />
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={closePanel}
              sx={{ color: 'rgba(255,255,255,0.6)', '&:hover': { color: '#fff', backgroundColor: 'rgba(255,255,255,0.1)' } }}>
              <CloseIcon sx={{ fontSize: 17 }} />
            </IconButton>
          </Box>
        </Box>

        {/* ── Agent tabs ── */}
        <Box sx={{
          px: 2, py: 0.75, backgroundColor: '#FFFFFF',
          borderBottom: '1px solid #E9EBF0',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {Object.values(INTENT).filter(m => m.label !== 'Error').map(m => (
              <Chip key={m.label}
                icon={<span style={{ fontSize: 11, marginLeft: 4 }}>{m.icon}</span>}
                label={m.label} size="small"
                sx={{ fontSize: 10, height: 21, fontWeight: 600,
                      backgroundColor: m.bg, color: m.color, cursor: 'default' }} />
            ))}
          </Box>
          <Tooltip title={showTools ? 'Hide info' : 'Show agent info'}>
            <IconButton size="small" onClick={() => setShowTools(v => !v)}
              sx={{ color: '#9CA3AF', p: 0.3 }}>
              {showTools ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
            </IconButton>
          </Tooltip>
        </Box>

        {/* ── Collapsible agent descriptions ── */}
        <Collapse in={showTools}>
          <Box sx={{ px: 2, py: 1, backgroundColor: '#FAFBFF', borderBottom: '1px solid #E9EBF0' }}>
            {Object.values(INTENT).filter(m => m.label !== 'Error').map(m => (
              <Box key={m.label} sx={{ display: 'flex', gap: 1, mb: 0.5 }}>
                <Typography sx={{ fontSize: 11, minWidth: 16 }}>{m.icon}</Typography>
                <Typography sx={{ fontSize: 11, color: '#374151', lineHeight: 1.5 }}>
                  <strong>{m.label}</strong> — {m.thinking}
                </Typography>
              </Box>
            ))}
          </Box>
        </Collapse>

        {/* ── Live data indicator ── */}
        <Box sx={{
          px: 2, py: 0.65,
          backgroundColor: isLive ? '#ECFDF5' : '#F9FAFB',
          borderBottom: `1px solid ${isLive ? '#A7F3D0' : '#E9EBF0'}`,
          display: 'flex', alignItems: 'flex-start', gap: 0.75,
        }}>
          <Box sx={{
            width: 7, height: 7, borderRadius: '50%', mt: '5px', flexShrink: 0,
            backgroundColor: isLive ? '#10B981' : '#9CA3AF',
            boxShadow: isLive ? '0 0 6px #10B981' : 'none',
            animation: isLive ? 'cascade-pulse 2s infinite' : 'none',
          }} />
          <Typography sx={{ fontSize: 10.5, fontWeight: 600, lineHeight: 1.5,
                           color: isLive ? '#065F46' : '#6B7280' }}>
            {isLive
              ? `Live · ${activeIVs.length} active: ${activeIVs.map(iv => iv.name).join(', ')} · ${boCount} outcome${boCount !== 1 ? 's' : ''}`
              : `${boCount} outcome${boCount !== 1 ? 's' : ''} loaded · No active sliders`
            }
          </Typography>
        </Box>
        <style>{`@keyframes cascade-pulse{0%,100%{opacity:1}50%{opacity:0.5}}`}</style>

        {/* ── Agent activity (which agents have contributed this session) ── */}
        <AgentActivityRow usedIntents={usedIntents} />

        {/* ── Sticky Recommendation Card (latest Goal/Advisor plan) ── */}
        {latestCard && (
          <RecommendationCard
            key={`${latestCard.kind}-${latestCard.title}-${latestCard.achieved_value}`}
            data={latestCard} onApply={handleApplyCard} disabled={isStreaming}
          />
        )}

        {/* ── Messages ── */}
        <Box className="cascade-messages"
          sx={{ flex: 1, overflowY: 'auto', px: 2, py: 1.75, backgroundColor: '#F8F9FF' }}>
          {isEmpty
            ? <EmptyState starters={starters} onStart={(msg, intent) => sendMessage(msg, intent || null, pageContext)} isStreaming={isStreaming} />
            : messages.map((msg, i) => (
                <Bubble key={i} msg={msg}
                  isLast={i === messages.length - 1}
                  isStreaming={isStreaming}
                  onFollowup={(q) => { if (!isStreaming) sendMessage(q, null, pageContext); }}
                  onCopy={() => {}} />
              ))
          }
          <div ref={bottomRef} />
        </Box>

        {/* ── Input ── */}
        <Box sx={{ px: 2, py: 1.25, borderTop: '1px solid #E9EBF0', backgroundColor: '#fff' }}>
          <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'flex-end' }}>
            {/* Voice input */}
            <Tooltip title={listening ? 'Stop recording' : 'Voice input'}>
              <IconButton onClick={handleVoice} size="small"
                sx={{
                  width: 38, height: 38, flexShrink: 0, borderRadius: '10px',
                  backgroundColor: listening ? '#FEF2F2' : '#F3F4F6',
                  color: listening ? '#DC2626' : '#6B7280',
                  '&:hover': { backgroundColor: listening ? '#FEE2E2' : '#E5E7EB' },
                  animation: listening ? 'cascade-pulse 1s infinite' : 'none',
                }}>
                {listening ? <MicIcon sx={{ fontSize: 18 }} /> : <MicOffIcon sx={{ fontSize: 18 }} />}
              </IconButton>
            </Tooltip>

            <TextField fullWidth multiline maxRows={4} inputRef={inputRef}
              placeholder="Ask about your KPIs, formulas, targets…"
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown} disabled={isStreaming} size="small"
              sx={{ '& .MuiOutlinedInput-root': {
                borderRadius: '12px', fontSize: 13, backgroundColor: '#F9FAFB',
                '& fieldset': { borderColor: '#E5E7EB' },
                '&:hover fieldset': { borderColor: '#C4B5FD' },
                '&.Mui-focused fieldset': { borderColor: '#4C3FDC', borderWidth: 1.5 },
              }}} />

            <IconButton onClick={handleSend} disabled={isStreaming || !input.trim()}
              sx={{
                width: 40, height: 40, flexShrink: 0, borderRadius: '12px',
                background: isStreaming || !input.trim()
                  ? '#E5E7EB' : 'linear-gradient(135deg, #4C3FDC, #7C3AED)',
                color: '#fff',
                '&:hover': { background: 'linear-gradient(135deg, #3B30C4, #6D28D9)' },
                '&.Mui-disabled': { backgroundColor: '#E5E7EB', color: '#9CA3AF' },
                boxShadow: isStreaming || !input.trim() ? 'none' : '0 3px 10px rgba(76,63,220,0.4)',
                transition: 'all 0.2s',
              }}>
              {isStreaming
                ? <CircularProgress size={16} thickness={5} sx={{ color: '#9CA3AF' }} />
                : <SendIcon sx={{ fontSize: 17 }} />}
            </IconButton>
          </Box>
          <Typography sx={{ fontSize: 10, color: '#9CA3AF', mt: 0.75, textAlign: 'center' }}>
            Google Gemini · Flash · Hybrid RAG · Live KPI data{isLive ? ` · ${activeIVs.length} active` : ''}
          </Typography>
        </Box>
      </Drawer>
    </>
  );
}
