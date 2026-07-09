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

// ---------------------------------------------------------------------------
// Pure-JS simulation cascade — runs entirely in the browser, no API calls.
// Mirrors the server-side simulation_service.recalculate() logic exactly.
//
// Formulas (from BRD / Excel "Simulation Formulae" sheet):
//
//   Intervention → L2:
//     intervention%  = intervention_percentage / 100
//     change%        = (impact_factor × intervention%) / 100
//     total_change%  = Σ change% from all linked interventions   [decimal, e.g. 0.05]
//     new_value      = default_value + (default_value × total_change%)
//
//   L2 → L1:
//     change%        = impact_factor × l2_total_change%          [decimal × decimal]
//     total_change%  = Σ change% from all linked L2s
//     new_value      = default_value + (default_value × total_change%)
//
//   L1 → Business Outcome:
//     change%        = impact_factor × l1_total_change%
//     total_change%  = Σ change% from all linked L1s
//     new_value      = default_value + (default_value × total_change%)
//
// IMPORTANT: all *_total_change maps hold DECIMAL fractions (e.g. 0.05 = 5%).
// improvement_percentage is stored as total_change * 100 (e.g. 5.0 for 5%),
// matching the backend. ImprovementIndicator derives its own % from
// current_value vs default_value so improvement_percentage is display-only.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Clears manual_override/manual_value flags on a metric collection.
//
// Manual overrides (from dragging an L2/L1/BO slider directly) are only
// meant to be transient: per spec, "On the next Intervention change, all
// mapped sliders should be recalculated again using the latest values and
// mapping rules." runLocalCascade() honors manual_override unconditionally
// (that's needed so a manual drag's own value sticks and cascades upward
// correctly at the moment it's dragged) — but that means the flag must be
// cleared BEFORE any Intervention-driven recalculation, or every metric
// that was ever manually touched would stay frozen forever, breaking the
// Intervention → L2 → L1 → BO mapping for the rest of the session.
// ---------------------------------------------------------------------------
function clearManualOverrides(metrics) {
  return metrics.map((m) =>
    m.manual_override ? { ...m, manual_override: false, manual_value: null } : m
  );
}

function runLocalCascade({ interventions, l2Metrics, l1Metrics, businessOutcomes }) {
  const r = (v, d = 4) => Math.round(v * 10 ** d) / 10 ** d;

  // ---- Step 1: Intervention → L2 ----------------------------------------
  // Accumulate total change% (decimal) for every L2 from all linked interventions.
  const l2TotalChange = {};
  l2Metrics.forEach((m) => { l2TotalChange[m.id] = 0; });

  interventions.forEach((iv) => {
    // intervention.percentage is 0–100 (slider value)
    const ivPct = iv.percentage ?? 0;
    // l2_metrics field comes from API as LinkedParent list (id + impact_factor)
    (iv.l2_metrics || iv.l2_links || []).forEach(({ id: l2Id, impact_factor }) => {
      if (l2TotalChange[l2Id] !== undefined) {
        // Excel stores slider 17% as 0.17 before applying:
        // Change% = Impact Factor × Intervention New Value % / 100.
        const interventionFraction = ivPct / 100;
        const changePct = (impact_factor * interventionFraction) / 100;
        l2TotalChange[l2Id] += changePct;
      }
    });
  });

  const newL2Metrics = l2Metrics.map((m) => {
    if (m.manual_override) {
      // Manual override: use manual_value, back-compute effective change for cascade
      const mv = m.manual_value ?? m.current_value;
      const effectiveChange = m.default_value !== 0
        ? (mv - m.default_value) / m.default_value
        : 0;
      // Overwrite l2TotalChange so L1 cascade uses the manual effective change
      l2TotalChange[m.id] = effectiveChange;
      return { ...m, current_value: mv, improvement_percentage: r(effectiveChange * 100, 2) };
    }
    const totalChange = l2TotalChange[m.id] ?? 0;
    const newValue = r(m.default_value + m.default_value * totalChange);
    return { ...m, current_value: newValue, improvement_percentage: r(totalChange * 100, 2) };
  });

  // ---- Step 2: L2 → L1 --------------------------------------------------
  // l2TotalChange[id] now contains the effective decimal change% for each L2
  // (either cascade-computed or back-computed from manual override).
  const l1TotalChange = {};
  l1Metrics.forEach((m) => { l1TotalChange[m.id] = 0; });

  newL2Metrics.forEach((l2) => {
    // Use the authoritative l2TotalChange (not l2.improvement_percentage which is *100)
    const l2Change = l2TotalChange[l2.id] ?? 0;
    // l1_metrics field comes from API as LinkedParent list
    (l2.l1_metrics || l2.l1_links || []).forEach(({ id: l1Id, impact_factor }) => {
      if (l1TotalChange[l1Id] !== undefined) {
        // Formula: change% = impact_factor × l2_total_change%  (both decimals)
        l1TotalChange[l1Id] += impact_factor * l2Change;
      }
    });
  });

  const newL1Metrics = l1Metrics.map((m) => {
    if (m.manual_override) {
      const mv = m.manual_value ?? m.current_value;
      const effectiveChange = m.default_value !== 0
        ? (mv - m.default_value) / m.default_value
        : 0;
      l1TotalChange[m.id] = effectiveChange;
      return { ...m, current_value: mv, improvement_percentage: r(effectiveChange * 100, 2) };
    }
    const totalChange = l1TotalChange[m.id] ?? 0;
    const newValue = r(m.default_value + m.default_value * totalChange);
    return { ...m, current_value: newValue, improvement_percentage: r(totalChange * 100, 2) };
  });

  // ---- Step 3: L1 → Business Outcome ------------------------------------
  const boTotalChange = {};
  businessOutcomes.forEach((b) => { boTotalChange[b.id] = 0; });

  newL1Metrics.forEach((l1) => {
    const l1Change = l1TotalChange[l1.id] ?? 0;
    // business_outcomes field comes from API as LinkedParent list
    (l1.business_outcomes || l1.bo_links || []).forEach(({ id: boId, impact_factor }) => {
      if (boTotalChange[boId] !== undefined) {
        boTotalChange[boId] += impact_factor * l1Change;
      }
    });
  });

  const newBusinessOutcomes = businessOutcomes.map((b) => {
    if (b.manual_override) {
      const mv = b.manual_value ?? b.current_value;
      const effectiveChange = b.default_value !== 0
        ? (mv - b.default_value) / b.default_value
        : 0;
      return { ...b, current_value: mv, improvement_percentage: r(effectiveChange * 100, 2) };
    }
    const totalChange = boTotalChange[b.id] ?? 0;
    const newValue = r(b.default_value + b.default_value * totalChange);
    return { ...b, current_value: newValue, improvement_percentage: r(totalChange * 100, 2) };
  });

  return {
    interventions,
    l2Metrics: newL2Metrics,
    l1Metrics: newL1Metrics,
    businessOutcomes: newBusinessOutcomes,
  };
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------
export const useKpiStore = create((set, get) => ({
  // ---- filters -----------------------------------------------------------
  verticalHorizontal: DEFAULT_VERTICAL,
  lob: DEFAULT_LOB,
  verticalOptions: [DEFAULT_VERTICAL],
  lobOptions: [DEFAULT_LOB],

  // ---- entity collections (always reflect DB-saved values on load) --------
  businessOutcomes: [],
  l1Metrics: [],
  l2Metrics: [],
  interventions: [],

  // ---- "live" collections: updated locally during slider drags -----------
  // These are what the UI renders. Populated from DB on fetch, then mutated
  // locally during drag WITHOUT any API calls.
  liveBusinessOutcomes: [],
  liveL1Metrics: [],
  liveL2Metrics: [],
  liveInterventions: [],

  loading: false,
  error: null,

  // ---- accordion expand/collapse state ------------------------------------
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

  // ---- snackbar / toast --------------------------------------------------
  toast: null,
  showToast: (message, severity = 'success') => set({ toast: { message, severity, key: Date.now() } }),
  clearToast: () => set({ toast: null }),

  // -----------------------------------------------------------------------
  // Filter loading
  // -----------------------------------------------------------------------
  loadFilterOptions: async () => {
    try {
      const verticalsRes = await filtersApi.verticals();
      const verticals = verticalsRes.data?.length ? verticalsRes.data : [DEFAULT_VERTICAL];
      const lobsRes = await filtersApi.lobs({ vertical_horizontal: get().verticalHorizontal });
      const lobs = lobsRes.data?.length ? lobsRes.data : [DEFAULT_LOB];
      // If the currently selected LOB is not in the new list, auto-select the first.
      const currentLob = get().lob;
      const lob = lobs.includes(currentLob) ? currentLob : lobs[0];
      set({ verticalOptions: verticals, lobOptions: lobs, lob });
    } catch (e) {
      console.error('Failed to load filter options', e);
    }
  },

  setVerticalHorizontal: async (value) => {
    set({ verticalHorizontal: value });
    // Fetch the LOB options for the new vertical, then auto-select the first one.
    try {
      const lobsRes = await filtersApi.lobs({ vertical_horizontal: value });
      const lobs = lobsRes.data?.length ? lobsRes.data : [DEFAULT_LOB];
      // Auto-select the first LOB for this vertical (user can change afterward).
      set({ lobOptions: lobs, lob: lobs[0] });
    } catch (e) {
      console.error('Failed to load LOB options', e);
    }
    // Also refresh vertical list in case it changed.
    try {
      const verticalsRes = await filtersApi.verticals();
      const verticals = verticalsRes.data?.length ? verticalsRes.data : [DEFAULT_VERTICAL];
      set({ verticalOptions: verticals });
    } catch (e) {
      console.error('Failed to load vertical options', e);
    }
    await get().fetchAll();
  },

  setLob: async (value) => {
    set({ lob: value });
    await get().fetchAll();
  },

  // -----------------------------------------------------------------------
  // fetchAll — loads data from the simulation snapshot endpoint so that
  // server-computed current_value / improvement_percentage are applied.
  // On refresh this always restores DB-saved values (slider temps are lost).
  // -----------------------------------------------------------------------
  fetchAll: async () => {
    const { verticalHorizontal, lob } = get();
    set({ loading: true, error: null });
    try {
      const params = { vertical_horizontal: verticalHorizontal, lob };

      // Use snapshot endpoint so server runs the full recalculation cascade.
      const snapRes = await simulationApi.snapshot(params);
      const snap = snapRes.data;

      const interventions = snap.interventions ?? [];
      const l2Metrics = snap.l2_metrics ?? [];
      const l1Metrics = snap.l1_metrics ?? [];
      const businessOutcomes = snap.business_outcomes ?? [];

      set({
        // Saved (DB) collections
        interventions,
        l2Metrics,
        l1Metrics,
        businessOutcomes,
        // Live collections start equal to DB values
        liveInterventions: interventions,
        liveL2Metrics: l2Metrics,
        liveL1Metrics: l1Metrics,
        liveBusinessOutcomes: businessOutcomes,
        loading: false,
      });
    } catch (e) {
      console.error(e);
      set({ loading: false, error: 'Failed to load KPI data. Is the backend running?' });
    }
  },

  // -----------------------------------------------------------------------
  // Generic CRUD used by create/edit pages
  // -----------------------------------------------------------------------
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

  // -----------------------------------------------------------------------
  // Intervention slider — DRAG TICK (no API, no DB write)
  // Updates liveInterventions percentage, then runs local cascade so all
  // dependent metrics update in real time as the user drags.
  // -----------------------------------------------------------------------
  updateInterventionValueLocal: (id, percentage) => {
    const state = get();

    // Update the live intervention list
    const liveInterventions = state.liveInterventions.map((iv) =>
      iv.id === id ? { ...iv, percentage } : iv
    );

    // BUG FIX: any L2/L1/BO manual overrides left over from a previous
    // manual drag must be cleared here. Otherwise runLocalCascade would
    // keep honoring the stale manual_value forever and Intervention changes
    // would stop propagating to that metric (and everything downstream of
    // it) for the rest of the session.
    const liveL2Metrics = clearManualOverrides(state.liveL2Metrics);
    const liveL1Metrics = clearManualOverrides(state.liveL1Metrics);
    const liveBusinessOutcomes = clearManualOverrides(state.liveBusinessOutcomes);

    // Run the pure-JS cascade
    const cascaded = runLocalCascade({
      interventions: liveInterventions,
      l2Metrics: liveL2Metrics,
      l1Metrics: liveL1Metrics,
      businessOutcomes: liveBusinessOutcomes,
    });

    set({
      liveInterventions: cascaded.interventions,
      liveL2Metrics: cascaded.l2Metrics,
      liveL1Metrics: cascaded.l1Metrics,
      liveBusinessOutcomes: cascaded.businessOutcomes,
    });
  },

  // -----------------------------------------------------------------------
  // Intervention slider — POINTER UP
  // Per spec: slider adjustments must NOT save to DB.
  // We only update the local "live" state and run the cascade — no API call.
  // On page refresh, DB values are restored via fetchAll.
  // -----------------------------------------------------------------------
  updateInterventionValue: (id, percentage) => {
    // This is intentionally the same as the drag-tick handler.
    // No DB write, no API call — temporary state only.
    get().updateInterventionValueLocal(id, percentage);
  },

  // -----------------------------------------------------------------------
  // Apply AI Recommendation — BATCH, FRONTEND-ONLY (no API, no DB write)
  // Used by the Cascade's "Apply Top Recommendation" button.
  // Matches intervention names against the CURRENTLY LOADED liveInterventions
  // only (already scoped to the active Vertical/LOB by fetchAll), so this can
  // never touch a record belonging to a different vertical or LOB.
  // Exact same persistence behavior as a manual slider drag: nothing is saved
  // until the user explicitly clicks Save/Create/Update on that record.
  // -----------------------------------------------------------------------
  applyRecommendationLocal: (interventions) => {
    const state = get();
    const notFound = [];
    const applied = [];

    let liveInterventions = state.liveInterventions;

    interventions.forEach(({ name, value }) => {
      const match = liveInterventions.find(
        (iv) => iv.name.toLowerCase() === name.toLowerCase()
      );
      if (match) {
        liveInterventions = liveInterventions.map((iv) =>
          iv.id === match.id ? { ...iv, percentage: value } : iv
        );
        applied.push({ name: match.name, value });
      } else {
        notFound.push(name);
      }
    });

    // BUG FIX: same reasoning as updateInterventionValueLocal — clear any
    // stale L2/L1/BO manual overrides so the recommended intervention
    // values fully recalculate the mapped hierarchy instead of being
    // blocked by a metric someone dragged earlier in the session.
    const liveL2Metrics = clearManualOverrides(state.liveL2Metrics);
    const liveL1Metrics = clearManualOverrides(state.liveL1Metrics);
    const liveBusinessOutcomes = clearManualOverrides(state.liveBusinessOutcomes);

    const cascaded = runLocalCascade({
      interventions: liveInterventions,
      l2Metrics: liveL2Metrics,
      l1Metrics: liveL1Metrics,
      businessOutcomes: liveBusinessOutcomes,
    });

    set({
      liveInterventions: cascaded.interventions,
      liveL2Metrics: cascaded.l2Metrics,
      liveL1Metrics: cascaded.l1Metrics,
      liveBusinessOutcomes: cascaded.businessOutcomes,
    });

    return { applied, notFound };
  },

  // -----------------------------------------------------------------------
  // Metric slider commit handler (L2 / L1 / Business Outcome)
  // Frontend-only — marks the dragged metric as manual_override, then
  // re-runs the full runLocalCascade so all downstream levels update
  // consistently using the same formula as the intervention cascade.
  // Does NOT save to DB.
  // -----------------------------------------------------------------------
  updateMetricCurrentValue: (column, id, current_value) => {
    const state = get();

    let liveInterventions = state.liveInterventions;
    let liveL2Metrics = state.liveL2Metrics;
    let liveL1Metrics = state.liveL1Metrics;
    let liveBusinessOutcomes = state.liveBusinessOutcomes;

    if (column === COLUMN_KEYS.L2_METRICS) {
      // Mark the dragged L2 as manually overridden; cascade will use its
      // back-computed change% for L1 and BO.
      liveL2Metrics = liveL2Metrics.map((m) => {
        if (m.id !== id) return m;
        return { ...m, current_value, manual_override: true, manual_value: current_value };
      });
    } else if (column === COLUMN_KEYS.L1_METRICS) {
      liveL1Metrics = liveL1Metrics.map((m) => {
        if (m.id !== id) return m;
        return { ...m, current_value, manual_override: true, manual_value: current_value };
      });
    } else if (column === COLUMN_KEYS.BUSINESS_OUTCOMES) {
      // BO is the top of the hierarchy — no downstream to cascade into.
      // Update directly without running the full cascade.
      liveBusinessOutcomes = liveBusinessOutcomes.map((b) => {
        if (b.id !== id) return b;
        const effectiveChange = b.default_value !== 0
          ? (current_value - b.default_value) / b.default_value
          : 0;
        return {
          ...b,
          current_value,
          improvement_percentage: Math.round(effectiveChange * 10000) / 100,
          manual_override: true,
          manual_value: current_value,
        };
      });
      set({ liveBusinessOutcomes });
      return;
    }

    // Re-run the full cascade so all levels stay consistent.
    // runLocalCascade handles manual_override by back-computing effective
    // change% from the manual_value, so it correctly propagates upward.
    const cascaded = runLocalCascade({
      interventions: liveInterventions,
      l2Metrics: liveL2Metrics,
      l1Metrics: liveL1Metrics,
      businessOutcomes: liveBusinessOutcomes,
    });

    set({
      liveL2Metrics: cascaded.l2Metrics,
      liveL1Metrics: cascaded.l1Metrics,
      liveBusinessOutcomes: cascaded.businessOutcomes,
    });
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

  // -----------------------------------------------------------------------
  // Structure & Access Control
  // -----------------------------------------------------------------------
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

  updateVerticalName: async (id, name) => {
    try {
      await structureApi.updateVertical(id, { name });
      await get().loadVerticalsDetailed();
      await get().loadFilterOptions();
      get().showToast('Vertical/Horizontal Level updated');
      return true;
    } catch (e) {
      console.error(e);
      get().showToast(e?.response?.data?.detail || 'Failed to update Vertical/Horizontal Level', 'error');
      return false;
    }
  },

  deleteVertical: async (id) => {
    try {
      await structureApi.deleteVertical(id);
      await get().loadVerticalsDetailed();
      await get().loadFilterOptions();
      get().showToast('Vertical/Horizontal Level deleted');
      return true;
    } catch (e) {
      console.error(e);
      get().showToast(e?.response?.data?.detail || 'Failed to delete Vertical/Horizontal Level', 'error');
      return false;
    }
  },

  addLobToVertical: async (verticalId, name) => {
    try {
      await structureApi.addLob(verticalId, { name });
      await get().loadVerticalsDetailed();
      await get().loadFilterOptions();
      get().showToast('LOB added');
      return true;
    } catch (e) {
      console.error(e);
      get().showToast(e?.response?.data?.detail || 'Failed to add LOB', 'error');
      return false;
    }
  },

  updateLobName: async (id, name) => {
    try {
      await structureApi.updateLob(id, { name });
      await get().loadVerticalsDetailed();
      await get().loadFilterOptions();
      get().showToast('LOB updated');
      return true;
    } catch (e) {
      console.error(e);
      get().showToast(e?.response?.data?.detail || 'Failed to update LOB', 'error');
      return false;
    }
  },

  deleteLob: async (id) => {
    try {
      await structureApi.deleteLob(id);
      await get().loadVerticalsDetailed();
      await get().loadFilterOptions();
      get().showToast('LOB deleted');
      return true;
    } catch (e) {
      console.error(e);
      get().showToast(e?.response?.data?.detail || 'Failed to delete LOB', 'error');
      return false;
    }
  },

  // -----------------------------------------------------------------------
  // User Onboarding
  // -----------------------------------------------------------------------
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
      get().showToast('Failed to delete user', 'error');
    }
  },
}));
