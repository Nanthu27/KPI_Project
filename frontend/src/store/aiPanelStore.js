import { create } from 'zustand';
import { agentsApi } from '../api/client';

export const AI_TABS = {
  INSIGHT: 'insight',
  GOAL: 'goal',
  EXCEL: 'excel',
  KNOWLEDGE: 'knowledge',
  DECISION: 'decision',
};

const TAB_LABELS = {
  [AI_TABS.INSIGHT]: 'Insight',
  [AI_TABS.GOAL]: 'Goal',
  [AI_TABS.EXCEL]: 'Excel',
  [AI_TABS.KNOWLEDGE]: 'Knowledge',
  [AI_TABS.DECISION]: 'Decision',
};

const SUGGESTED_QUESTIONS = {
  [AI_TABS.INSIGHT]: [
    'Why did Cash Conversion Cycle change?',
    'What drove the change in DSO?',
    'Explain the current simulation result',
  ],
  [AI_TABS.GOAL]: [
    'I want DSO to reach 30 days',
    'How do I reduce Bad Debt Ratio to 1%?',
    'What does it take to reach 90% Collection Efficiency?',
  ],
  [AI_TABS.EXCEL]: [
    'How is DSO calculated?',
    'Which cell drives Collection Efficiency?',
    'Show the formula path for Cash Conversion Cycle',
  ],
  [AI_TABS.KNOWLEDGE]: [
    'What is Cash Conversion Cycle?',
    'What does the BRD say about benchmarks?',
    'Define Days Sales Outstanding',
  ],
  [AI_TABS.DECISION]: [
    'I have a budget of $5,000 — what should I prioritize?',
    'Best use of a $10,000 budget?',
    'Which option gives the best ROI?',
  ],
};

function emptyTabState() {
  return { messages: [], loading: false };
}

export const useAiPanelStore = create((set, get) => ({
  panelOpen: false,
  activeTab: AI_TABS.INSIGHT,
  tabs: {
    [AI_TABS.INSIGHT]: emptyTabState(),
    [AI_TABS.GOAL]: emptyTabState(),
    [AI_TABS.EXCEL]: emptyTabState(),
    [AI_TABS.KNOWLEDGE]: emptyTabState(),
    [AI_TABS.DECISION]: emptyTabState(),
  },

  togglePanel: () => set((s) => ({ panelOpen: !s.panelOpen })),
  openPanel: () => set({ panelOpen: true }),
  closePanel: () => set({ panelOpen: false }),
  setActiveTab: (tab) => set({ activeTab: tab }),

  getTabLabel: (tab) => TAB_LABELS[tab],
  getSuggestedQuestions: (tab) => SUGGESTED_QUESTIONS[tab] || [],

  sendMessage: async (tab, userText, context) => {
    const { vertical_horizontal, lob, budget } = context;

    set((s) => ({
      tabs: {
        ...s.tabs,
        [tab]: {
          ...s.tabs[tab],
          loading: true,
          messages: [...s.tabs[tab].messages, { role: 'user', text: userText }],
        },
      },
    }));

    try {
      let response;
      if (tab === AI_TABS.INSIGHT) {
        response = await agentsApi.insight({ vertical_horizontal, lob, user_question: userText });
      } else if (tab === AI_TABS.GOAL) {
        response = await agentsApi.goal({ vertical_horizontal, lob, user_question: userText });
      } else if (tab === AI_TABS.EXCEL) {
        response = await agentsApi.excel({ metric_name: userText, metric_level: 'l1', user_question: userText });
      } else if (tab === AI_TABS.KNOWLEDGE) {
        response = await agentsApi.knowledge({ user_question: userText });
      } else if (tab === AI_TABS.DECISION) {
        response = await agentsApi.decision({ vertical_horizontal, lob, budget: budget || 0, user_question: userText });
      }

      const data = response.data;
      set((s) => ({
        tabs: {
          ...s.tabs,
          [tab]: {
            ...s.tabs[tab],
            loading: false,
            messages: [...s.tabs[tab].messages, { role: 'agent', tab, data }],
          },
        },
      }));
    } catch (e) {
      console.error(e);
      const errorText = e?.response?.data?.detail || 'Something went wrong reaching this agent. Please try again.';
      set((s) => ({
        tabs: {
          ...s.tabs,
          [tab]: {
            ...s.tabs[tab],
            loading: false,
            messages: [...s.tabs[tab].messages, { role: 'agent', tab, data: { response_text: errorText, _error: true } }],
          },
        },
      }));
    }
  },

  clearTab: (tab) => set((s) => ({ tabs: { ...s.tabs, [tab]: emptyTabState() } })),
}));
