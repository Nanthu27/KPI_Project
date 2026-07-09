/**
 * Cascade Zustand Store — Production Version
 *
 * Key: starters built from LIVE page data — never hardcoded metric names.
 * pageContext passed to every API call so agent always has current values.
 */
import { create } from 'zustand';
import { streamCascadeMessage } from '../services/cascadeApi';

// Fixed 1:1 suggestion → agent mapping (see PATCH_NOTES / bug report
// "Incorrect Intent Mapping"). Every starter now carries an explicit
// `intent` that is sent to the backend as `intent_override`, so the agent
// that answers a click is deterministic and NEVER re-classified by the
// LLM/regex router. Before this, starters had no intent at all — the
// backend had to guess from message text alone, which is how clicking
// "🎯 How can I improve X?" could land on Decision Advisor instead of the
// Goal/Improvement agent depending on exact wording.
//
//   💡 → insight   (Explanation Agent  — why did my KPIs change)
//   🎯 → goal       (Goal/Improvement Agent — how do I improve this metric)
//   🔍 → trace      (Formula Trace Agent)
//   📊 → insight    (Impact Analysis — why did this intervention change things)
//   ⭐ → advisor     (Decision Advisor — strategy ranking, only on explicit ask)
function buildStarters(pageContext) {
  const bos  = pageContext?.businessOutcomes  || [];
  const ivs  = pageContext?.activeInterventions || [];
  const l1s  = pageContext?.l1Metrics || [];

  const firstBO = bos[0]?.name;
  const firstIV = ivs[0]?.name;
  const firstL1 = l1s[0]?.name;

  const starters = [
    { emoji:'💡', label: 'Why did my KPIs change?', message: 'Why did my KPIs change?', intent: 'insight' },
  ];

  if (firstBO) {
    starters.push({ emoji:'🎯', label: `How can I improve ${firstBO}?`, message: `How can I improve ${firstBO}?`, intent: 'goal' });
    starters.push({ emoji:'🔍', label: `Trace formula for ${firstBO}`, message: `Show me the formula path for ${firstBO}`, intent: 'trace' });
  } else {
    starters.push({ emoji:'🎯', label: 'How can I improve my business outcomes?', message: 'How can I improve my business outcomes?', intent: 'goal' });
    starters.push({ emoji:'🔍', label: 'How is this KPI calculated?', message: 'How is this KPI calculated?', intent: 'trace' });
  }

  if (firstIV) {
    starters.push({ emoji:'📊', label: `Why did ${firstIV} change things?`, message: `Explain why ${firstIV} changed my KPIs`, intent: 'insight' });
  }

  starters.push({ emoji:'⭐', label: 'Recommend the best intervention strategy', message: 'Recommend the best intervention strategy', intent: 'advisor' });

  return starters.slice(0, 5);
}

export const useCascadeStore = create((set, get) => ({
  isOpen: false,
  openPanel:  () => set({ isOpen: true }),
  closePanel: () => set({ isOpen: false }),
  togglePanel:() => set(s => ({ isOpen: !s.isOpen })),

  messages: [],
  isStreaming: false,
  starters: buildStarters(null),
  context: {},

  clearMessages: () => set({ messages: [] }),
  setContext: (ctx) => set(s => ({ context: { ...s.context, ...ctx } })),

  updateStarters: (pageContext) => set({ starters: buildStarters(pageContext) }),

  sendMessage: async (userText, intentOverride = null, pageContext = null) => {
    if (!userText.trim()) return;
    const { messages, context } = get();

    const userMsg = { role: 'user', content: userText };
    set({ messages: [...messages, userMsg], isStreaming: true });

    // Placeholder bubble (shows thinking animation)
    set(s => ({
      messages: [...s.messages, { role: 'assistant', content: '', intent: intentOverride || null, isStreaming: true }],
    }));

    try {
      // The backend scopes every AI tool call (insight, goal, trace, advisor)
      // to a vertical_horizontal + lob pair. Previously these were never
      // sent at all — `context` was never populated via setContext(), and
      // even when a vertical was known it only lived inside
      // pageContext.filters.vertical, never the top-level fields the
      // backend schema actually reads. That silent gap is what let another
      // vertical's (e.g. Finance & Accounting) live data leak into
      // responses shown on a different vertical's page.
      const filters = pageContext?.filters || {};
      const request = {
        message: userText,
        history: messages.slice(-8).map(m => ({ role: m.role, content: m.content })),
        intent_override: intentOverride,
        vertical_horizontal: filters.vertical || filters.vertical_horizontal || null,
        lob: filters.lob || null,
        ...context,
        page_context: pageContext ? {
          active_interventions: pageContext.activeInterventions || [],
          business_outcomes:    pageContext.businessOutcomes    || [],
          l1_metrics:           pageContext.l1Metrics           || [],
          l2_metrics:           pageContext.l2Metrics           || [],
          filters:              pageContext.filters              || {},
        } : null,
      };

      let fullText = '';
      let meta = null;

      for await (const event of streamCascadeMessage(request)) {
        if (event.type === 'meta') {
          meta = event;
          // Set intent badge immediately on first event
          set(s => {
            const msgs = [...s.messages];
            msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], intent: meta.intent };
            return { messages: msgs };
          });
        } else if (event.type === 'chunk') {
          fullText += event.text;
          set(s => {
            const msgs = [...s.messages];
            msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: fullText };
            return { messages: msgs };
          });
        } else if (event.type === 'error') {
          fullText += `\n\n⚠️ ${event.error}`;
        } else if (event.type === 'done') {
          break;
        }
      }

      set(s => {
        const msgs = [...s.messages];
        msgs[msgs.length - 1] = {
          role: 'assistant',
          content: fullText || '(no response received)',
          intent: meta?.intent || intentOverride || 'knowledge',
          followups: meta?.followups || [],
          // Deterministic slider-apply payload from the backend (Advisor
          // Mode 2). See CascadePanel's applyAction effect — this replaces
          // the old approach of regex-scraping "**Name**: NN%" out of the
          // chat reply text, which broke whenever wording changed.
          applyAction: meta?.apply_action || null,
          // Structured plan for the sticky Recommendation Card — see
          // backend/app/ai/cascade/agent.py::_recommendation_card_data.
          // null for intents with no actionable plan to pin (Insight,
          // Knowledge, Trace, What-If, Advisor apply-confirmation).
          cardData: meta?.card_data || null,
          isStreaming: false,
        };
        return { messages: msgs, isStreaming: false };
      });

    } catch (err) {
      set(s => {
        const msgs = [...s.messages];
        msgs[msgs.length - 1] = {
          role: 'assistant',
          content: `⚠️ **Connection error:** ${err.message}\n\nCheck that the backend is running at port 8000 and \`GEMINI_API_KEY\` is set in \`backend/.env\`.`,
          intent: 'error',
          isStreaming: false,
        };
        return { messages: msgs, isStreaming: false };
      });
    }
  },

  // Frontend-only — exactly like a slider drag. Never calls the backend,
  // never writes to the database. Updates the live simulation state and
  // re-runs the cascade. Caller passes the kpiStore's applyRecommendationLocal
  // function in as `applyFn` (App.jsx wires this from useKpiStore()).
  _lastApplySignature: null,
  _lastApplyAt: 0,
  applyRecommendation: async (interventions, applyFn) => {
    if (!applyFn) {
      console.error('applyRecommendation: no applyFn provided from kpiStore');
      return;
    }

    // Dedupe guard: the same exact apply can otherwise fire twice from two
    // different triggers in the same turn (e.g. the sticky card's Apply
    // button AND the legacy per-bubble Advisor apply button both reacting
    // to one click), producing two back-to-back, near-identical
    // confirmation bubbles. A second call with the SAME intervention
    // payload within a short window is treated as a duplicate and dropped.
    const signature = JSON.stringify(
      [...interventions].sort((a, b) => a.name.localeCompare(b.name))
    );
    const now = Date.now();
    const { _lastApplySignature, _lastApplyAt } = get();
    if (signature === _lastApplySignature && now - _lastApplyAt < 1500) {
      return;
    }
    set({ _lastApplySignature: signature, _lastApplyAt: now });

    const { applied, notFound } = applyFn(interventions);

    // One short, natural-sounding line instead of a formal notice. Consider
    // moving the full "nothing is saved to the DB" explanation to a
    // tooltip/help icon near the Apply button instead of repeating it as a
    // paragraph in chat every single time (not yet built — noted for later).
    const sliderList = applied.map(a => `${a.name} ${a.value}%`).join(', ');
    const content = applied.length > 0
      ? `✅ Done — set ${sliderList}. (Just a live preview, like dragging the sliders.)${
          notFound.length > 0 ? ` Couldn't find on this page: ${notFound.join(', ')}.` : ''
        }`
      : `⚠️ None of those (${interventions.map(i => i.name).join(', ')}) are on the current page — they may belong to a different Vertical/LOB.`;

    set(s => ({
      messages: [...s.messages, {
        role: 'assistant',
        content,
        // Deliberately NOT 'advisor' or any agent key — this confirmation
        // is a deterministic frontend action, not any one agent's
        // response, and mislabeling it (e.g. always "Decision Advisor"
        // even when a Goal recommendation was what got applied) was its
        // own bug. An intent with no entry in CascadePanel's INTENT map
        // renders as a plain, unbadged confirmation bubble instead.
        intent: 'system',
        isApplyConfirmation: true,
        isStreaming: false,
      }],
    }));

    return { applied, notFound };
  },

  // Same computation as applyRecommendation, but for the auto-apply path
  // (a chat message that already carries an apply_action, e.g. typing
  // "Apply the top recommendation to my sliders"). That path used to call
  // applyRecommendation() above, which APPENDED a second "✅ Done — ..."
  // bubble right after the agent's own "the strategy is now being
  // applied..." message — one action, two back-to-back near-duplicate
  // bubbles. This instead rewrites the ORIGINAL message's content in place
  // with the confirmation text, so the whole thing reads as one response.
  applyRecommendationToMessage: async (messageIndex, interventions, applyFn) => {
    if (!applyFn) {
      console.error('applyRecommendationToMessage: no applyFn provided from kpiStore');
      return;
    }

    const signature = JSON.stringify(
      [...interventions].sort((a, b) => a.name.localeCompare(b.name))
    );
    const now = Date.now();
    const { _lastApplySignature, _lastApplyAt } = get();
    if (signature === _lastApplySignature && now - _lastApplyAt < 1500) {
      return;
    }
    set({ _lastApplySignature: signature, _lastApplyAt: now });

    const { applied, notFound } = applyFn(interventions);

    const sliderList = applied.map(a => `${a.name} ${a.value}%`).join(', ');
    const content = applied.length > 0
      ? `✅ Done — set ${sliderList}. (Just a live preview, like dragging the sliders.)${
          notFound.length > 0 ? ` Couldn't find on this page: ${notFound.join(', ')}.` : ''
        }`
      : `⚠️ None of those (${interventions.map(i => i.name).join(', ')}) are on the current page — they may belong to a different Vertical/LOB.`;

    set(s => ({
      messages: s.messages.map((m, i) =>
        i === messageIndex ? { ...m, content, isApplyConfirmation: true } : m
      ),
    }));

    return { applied, notFound };
  },
}));
