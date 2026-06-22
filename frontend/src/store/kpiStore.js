import { create } from 'zustand';
import {
  businessOutcomesApi,
  l1MetricsApi,
  l2MetricsApi,
  interventionsApi,
  simulationApi,
  filtersApi,
  structureApi,
  usersApi,
  uploadExcel,
} from '../api/client';

const DEFAULT_VERTICAL = 'Finance & Accounting';
const DEFAULT_LOB = 'Order to Cash';

export const COLUMN_KEYS = {
  BUSINESS_OUTCOMES: 'businessOutcomes',
  L1_METRICS: 'l1Metrics',
  L2_METRICS: 'l2Metrics',
  INTERVENTIONS: 'interventions',
};

const apiByColumn = {
  [COLUMN_KEYS.BUSINESS_OUTCOMES]: businessOutcomesApi,
  [COLUMN_KEYS.L1_METRICS]: l1MetricsApi,
  [COLUMN_KEYS.L2_METRICS]: l2MetricsApi,
  [COLUMN_KEYS.INTERVENTIONS]: interventionsApi,
};

export const useKpiStore = create((set, get) => ({
  // ---- filters -----------------------------------------------------------
  verticalHorizontal: DEFAULT_VERTICAL,
  lob: DEFAULT_LOB,
  verticalOptions: [DEFAULT_VERTICAL],
  lobOptions: [DEFAULT_LOB],

  // ---- entity collections -------------------------------------------------
  businessOutcomes: [],
  l1Metrics: [],
  l2Metrics: [],
  interventions: [],

  loading: false,
  error: null,

  // ---- accordion expand/collapse state (replaces drag & drop) -------------
  // All 4 columns start expanded so the board looks the same as before on
  // first load; the user can collapse any column to save space.
  expandedColumns: {
    [COLUMN_KEYS.BUSINESS_OUTCOMES]: true,
    [COLUMN_KEYS.L1_METRICS]: true,
    [COLUMN_KEYS.L2_METRICS]: true,
    [COLUMN_KEYS.INTERVENTIONS]: true,
  },
  toggleColumn: (column) =>
    set((state) => ({
      expandedColumns: { ...state.expandedColumns, [column]: !state.expandedColumns[column] },
    })),

  // ---- snackbar / toast -----------------------------------------------------
  toast: null,
  showToast: (message, severity = 'success') => set({ toast: { message, severity, key: Date.now() } }),
  clearToast: () => set({ toast: null }),

  // ---------------------------------------------------------------------
  // Filter loading
  // ---------------------------------------------------------------------
  loadFilterOptions: async () => {
    try {
      const verticalsRes = await filtersApi.verticals();
      const verticals = verticalsRes.data?.length ? verticalsRes.data : [DEFAULT_VERTICAL];
      const lobsRes = await filtersApi.lobs({ vertical_horizontal: get().verticalHorizontal });
      const lobs = lobsRes.data?.length ? lobsRes.data : [DEFAULT_LOB];
      set({ verticalOptions: verticals, lobOptions: lobs });
    } catch (e) {
      // Non-fatal: fall back to defaults already in state.
      console.error('Failed to load filter options', e);
    }
  },

  setVerticalHorizontal: async (value) => {
    set({ verticalHorizontal: value });
    await get().loadFilterOptions();
    await get().fetchAll();
  },

  setLob: async (value) => {
    set({ lob: value });
    await get().fetchAll();
  },

  // ---------------------------------------------------------------------
  // Fetch all 4 collections scoped to current filters
  // ---------------------------------------------------------------------
  fetchAll: async () => {
    const { verticalHorizontal, lob } = get();
    set({ loading: true, error: null });
    try {
      const params = { vertical_horizontal: verticalHorizontal, lob };
      const [bo, l1, l2, iv] = await Promise.all([
        businessOutcomesApi.list(params),
        l1MetricsApi.list(params),
        l2MetricsApi.list(params),
        interventionsApi.list(params),
      ]);
      set({
        businessOutcomes: bo.data,
        l1Metrics: l1.data,
        l2Metrics: l2.data,
        interventions: iv.data,
        loading: false,
      });
    } catch (e) {
      console.error(e);
      set({ loading: false, error: 'Failed to load KPI data. Is the backend running?' });
    }
  },

  // ---------------------------------------------------------------------
  // Generic CRUD used by the create/edit pages
  // ---------------------------------------------------------------------
  createRecord: async (column, payload) => {
    const repo = apiByColumn[column];
    await repo.create({
      ...payload,
      vertical_horizontal: get().verticalHorizontal,
      lob: get().lob,
    });
    await get().fetchAll();
    get().showToast('Created successfully');
  },

  updateRecord: async (column, id, payload) => {
    const repo = apiByColumn[column];
    await repo.update(id, payload);
    await get().fetchAll();
    get().showToast('Updated successfully');
  },

  deleteRecord: async (column, id) => {
    const repo = apiByColumn[column];
    await repo.remove(id);
    await get().fetchAll();
    get().showToast('Deleted');
  },

  // ---------------------------------------------------------------------
  // Slider handlers
  // ---------------------------------------------------------------------
  updateInterventionValue: async (id, percentage) => {
    set((state) => ({
      interventions: state.interventions.map((iv) =>
        iv.id === id ? { ...iv, percentage } : iv
      ),
    }));
    try {
      await interventionsApi.update(id, { percentage });
      await get().fetchAll();
    } catch (e) {
      console.error(e);
      get().showToast('Failed to update intervention', 'error');
    }
  },

  updateMetricCurrentValue: async (column, id, current_value) => {
    try {
      await apiByColumn[column].update(id, { default_value: current_value });
      await get().fetchAll();
    } catch (e) {
      console.error(e);
      get().showToast('Failed to update metric', 'error');
    }
  },

  resetSimulation: async () => {
    await simulationApi.reset();
    await get().fetchAll();
    get().showToast('Simulation reset to baseline');
  },

  uploadExcelFile: async (file) => {
    set({ loading: true });
    try {
      const res = await uploadExcel(file);
      await get().loadFilterOptions();
      await get().fetchAll();
      const { business_outcomes_created, l1_metrics_created, l2_metrics_created, interventions_created, warnings } = res.data;
      const total = business_outcomes_created + l1_metrics_created + l2_metrics_created + interventions_created;
      if (total === 0) {
        get().showToast(warnings?.[0] || 'No matching sheets found in workbook', 'error');
      } else {
        get().showToast(`Imported ${total} records from Excel`);
      }
      return res.data;
    } catch (e) {
      console.error(e);
      get().showToast(e?.response?.data?.detail || 'Excel upload failed', 'error');
      throw e;
    } finally {
      set({ loading: false });
    }
  },

  // ---------------------------------------------------------------------
  // Structure & Access Control: Mapping (Verticals / LOBs)
  // ---------------------------------------------------------------------
  verticalsDetailed: [],

  loadVerticalsDetailed: async () => {
    try {
      const res = await structureApi.listVerticalsDetailed();
      set({ verticalsDetailed: res.data });
    } catch (e) {
      console.error(e);
      get().showToast('Failed to load Vertical/LOB mappings', 'error');
    }
  },

  createVertical: async (name, lobNames) => {
    try {
      await structureApi.createVertical({ name, lobs: lobNames });
      await get().loadVerticalsDetailed();
      await get().loadFilterOptions();
      get().showToast('Vertical/Horizontal Level created');
      return true;
    } catch (e) {
      console.error(e);
      get().showToast(e?.response?.data?.detail || 'Failed to create Vertical/Horizontal Level', 'error');
      return false;
    }
  },

  // ---------------------------------------------------------------------
  // Structure & Access Control: User Onboarding
  // ---------------------------------------------------------------------
  users: [],
  roster: [],

  loadUsers: async () => {
    try {
      const [usersRes, rosterRes] = await Promise.all([usersApi.list(), usersApi.roster()]);
      set({ users: usersRes.data, roster: rosterRes.data });
    } catch (e) {
      console.error(e);
      get().showToast('Failed to load users', 'error');
    }
  },

  addUser: async (name) => {
    try {
      await usersApi.create({ name });
      await get().loadUsers();
      get().showToast('User added');
    } catch (e) {
      console.error(e);
      get().showToast('Failed to add user', 'error');
    }
  },

  updateUser: async (id, payload) => {
    try {
      await usersApi.update(id, payload);
      await get().loadUsers();
    } catch (e) {
      console.error(e);
      get().showToast('Failed to update user', 'error');
    }
  },

  deleteUser: async (id) => {
    try {
      await usersApi.remove(id);
      await get().loadUsers();
      get().showToast('User removed');
    } catch (e) {
      console.error(e);
      get().showToast('Failed to remove user', 'error');
    }
  },
}));
