import { useEffect, useRef, useState } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Box, Snackbar, Alert, CircularProgress, Typography } from '@mui/material';

import Header from './components/Header';
import FilterBar from './components/FilterBar';
import KPIColumn from './components/KPIColumn';
import KPICard from './components/KPICard';
import InterventionCard from './components/InterventionCard';
import ConfirmDeleteDialog from './components/ConfirmDeleteDialog';
import UserGuidePopover from './components/UserGuidePopover';
import CreateL1MetricPage from './pages/CreateL1MetricPage';
import CreateL2MetricPage from './pages/CreateL2MetricPage';
import CreateBusinessOutcomePage from './pages/CreateBusinessOutcomePage';
import CreateInterventionPage from './pages/CreateInterventionPage';
import StructureAccessControlPage from './pages/StructureAccessControlPage';
import MappingListPage from './pages/MappingListPage';
import AddLobPage from './pages/AddLobPage';
import { useKpiStore, COLUMN_KEYS } from './store/kpiStore';
import { COLORS } from './theme/theme';
import CascadePanel from './ai/components/CascadePanel';
import CascadeButton from './ai/components/CascadeButton';
import { useCascadeStore } from './ai/store/cascadeStore';

const COLUMN_CONFIG = [
  { key: COLUMN_KEYS.BUSINESS_OUTCOMES, title: 'Business Outcomes', isFirstColumn: true, createPath: '/business-outcomes/new', editPath: (id) => `/business-outcomes/${id}/edit` },
  { key: COLUMN_KEYS.L1_METRICS, title: 'L1 Metrics', isFirstColumn: false, createPath: '/l1-metrics/new', editPath: (id) => `/l1-metrics/${id}/edit` },
  { key: COLUMN_KEYS.L2_METRICS, title: 'L2 Metrics', isFirstColumn: false, createPath: '/l2-metrics/new', editPath: (id) => `/l2-metrics/${id}/edit` },
  { key: COLUMN_KEYS.INTERVENTIONS, title: 'Intervention', isFirstColumn: false, createPath: '/interventions/new', editPath: (id) => `/interventions/${id}/edit` },
];

function KpiBoard() {
  const navigate = useNavigate();
  const {
    verticalHorizontal, lob, verticalOptions, lobOptions,
    liveBusinessOutcomes, liveL1Metrics, liveL2Metrics, liveInterventions,
    loading, error, toast,
    loadFilterOptions, setVerticalHorizontal, setLob, fetchAll,
    deleteRecord,
    updateInterventionValueLocal,  // drag-tick: local cascade only, no API
    updateInterventionValue,       // pointer-up: local cascade only, no API
    updateMetricCurrentValue,      // pointer-up: local cascade only, no API
    applyRecommendationLocal,      // Cascade "Apply" — local cascade only, no API, no DB write
    clearToast,
  } = useKpiStore();

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const userGuideButtonRef = useRef(null);

  useEffect(() => {
    (async () => {
      await loadFilterOptions();
      await fetchAll();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Always render the "live" collections so drag-time cascades show instantly.
  // These reset to DB values on page refresh via fetchAll → snapshot endpoint.
  const dataByColumn = {
    [COLUMN_KEYS.BUSINESS_OUTCOMES]: liveBusinessOutcomes,
    [COLUMN_KEYS.L1_METRICS]: liveL1Metrics,
    [COLUMN_KEYS.L2_METRICS]: liveL2Metrics,
    [COLUMN_KEYS.INTERVENTIONS]: liveInterventions,
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    await deleteRecord(deleteTarget.column, deleteTarget.record.id);
    setDeleteTarget(null);
  };

  return (
    <>
      <Box sx={{ minHeight: '100vh', backgroundColor: '#3A3950', p: 2, display: 'flex', justifyContent: 'center' }}>
        <Box id="kpi-app-root" sx={{ width: '100%', maxWidth: 1800, height: 'calc(100vh - 8px)', backgroundColor: COLORS.background, borderRadius: '4px', overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 10px 40px rgba(0,0,0,0.3)' }}>
          <Header onUploadExcel={(file) => useKpiStore.getState().uploadExcelFile(file)} />
          <FilterBar
            verticalHorizontal={verticalHorizontal}
            lob={lob}
            verticalOptions={verticalOptions}
            lobOptions={lobOptions}
            onChangeVertical={setVerticalHorizontal}
            onChangeLob={setLob}
            onStructureClick={() => navigate('/structure/new-vertical')}
            onUserGuideClick={() => setGuideOpen(true)}
            userGuideButtonRef={userGuideButtonRef}
          />
          <Box sx={{ position: 'relative', flex: 1, minHeight: 0 }}>
            {loading && (
              <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(236,236,236,0.6)', zIndex: 10 }}>
                <CircularProgress sx={{ color: COLORS.primary }} />
              </Box>
            )}
            {error && <Box sx={{ p: 4 }}><Typography color="error">{error}</Typography></Box>}
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 2, p: 2, height: 'calc(100% - 20px)', minHeight: 0, alignItems: 'stretch', overflow: 'hidden' }}>
              {COLUMN_CONFIG.map(({ key, title, isFirstColumn, createPath, editPath }) => (
                <KPIColumn
                  key={key}
                  title={title}
                  column={key}
                  isFirstColumn={isFirstColumn}
                  onAddClick={() => navigate(createPath)}
                >
                  {dataByColumn[key].map((record) =>
                    key === COLUMN_KEYS.INTERVENTIONS ? (
                      <InterventionCard
                        key={record.id}
                        record={record}
                        onEdit={(r) => navigate(editPath(r.id))}
                        onDelete={(r) => setDeleteTarget({ column: key, record: r })}
                        // Drag tick: local state only, no API
                        onChangeValue={(id, v) => updateInterventionValueLocal(id, v)}
                        // Pointer up: persist to DB + trigger simulation cascade
                        onCommitValue={(id, v) => updateInterventionValue(id, v)}
                      />
                    ) : (
                      <KPICard
                        key={record.id}
                        record={record}
                        onEdit={(r) => navigate(editPath(r.id))}
                        onDelete={(r) => setDeleteTarget({ column: key, record: r })}
                        // Called once on pointer release — pure local cascade, no DB write
                        onMetricChange={(id, value) => updateMetricCurrentValue(key, id, value)}
                      />
                    )
                  )}
                  {dataByColumn[key].length === 0 && !loading && (
                    <Typography sx={{ fontSize: 13, color: COLORS.textMuted, textAlign: 'center', mt: 4 }}>
                      No items yet. Click "+" to add one.
                    </Typography>
                  )}
                </KPIColumn>
              ))}
            </Box>
          </Box>
        </Box>
      </Box>

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        recordName={deleteTarget?.record?.name}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
      />

      <UserGuidePopover
        open={guideOpen}
        anchorEl={userGuideButtonRef.current}
        onClose={() => setGuideOpen(false)}
      />

      <Snackbar open={!!toast} autoHideDuration={3000} onClose={clearToast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} key={toast?.key}>
        {toast ? <Alert severity={toast.severity} onClose={clearToast}>{toast.message}</Alert> : undefined}
      </Snackbar>

      {/* ── Cascade AI — additive, no existing code modified ── */}
      <CascadePanel
        onApplyToSliders={applyRecommendationLocal}
        pageContext={{
          // NOTE: intentionally NOT filtered to percentage > 0. The Cascade
          // backend needs the full list of interventions that exist on this
          // page to match names the user types in chat (e.g. "TP Simulation
          // 11%") even when that slider hasn't been touched yet. Filtering
          // here to only already-active sliders was why WHATIF questions
          // failed to match anything at the initial (all-zero) state, and
          // silently dropped named-but-untouched interventions from the
          // answer once some (but not all) sliders had been moved. The
          // backend derives its own "currently active" (>0%) subset from
          // this same list internally wherever that distinction matters.
          activeInterventions: liveInterventions?.map(iv => ({ name: iv.name, percentage: iv.percentage })),
          businessOutcomes: liveBusinessOutcomes?.map(bo => ({ name: bo.name, default_value: bo.default_value, current_value: bo.current_value, improvement_pct: bo.improvement_percentage })),
          l1Metrics: liveL1Metrics?.map(m => ({ name: m.name, default_value: m.default_value, current_value: m.current_value, improvement_pct: m.improvement_percentage })),
          l2Metrics: liveL2Metrics?.map(m => ({ name: m.name, default_value: m.default_value, current_value: m.current_value, improvement_pct: m.improvement_percentage })),
          filters: { vertical: verticalHorizontal, lob },
        }}
      />
      <CascadeButton />
    </>
  );
}

export default function App() {
  const location = useLocation();
  const closePanel = useCascadeStore(s => s.closePanel);
  const isHome = location.pathname === '/';

  // Close the Cascade panel only on a REAL navigation away from the home
  // board — not on every re-render or unrelated unmount, which is what
  // caused it to close on unrelated clicks before. Skips the very first
  // render (isHome starts true, nothing to close yet).
  useEffect(() => {
    if (!isHome) {
      closePanel();
    }
  }, [isHome, closePanel]);

  return (
    <Routes>
      <Route path="/" element={<KpiBoard />} />
      <Route path="/business-outcomes/new" element={<CreateBusinessOutcomePage />} />
      <Route path="/business-outcomes/:id/edit" element={<CreateBusinessOutcomePage />} />
      <Route path="/l1-metrics/new" element={<CreateL1MetricPage />} />
      <Route path="/l1-metrics/:id/edit" element={<CreateL1MetricPage />} />
      <Route path="/l2-metrics/new" element={<CreateL2MetricPage />} />
      <Route path="/l2-metrics/:id/edit" element={<CreateL2MetricPage />} />
      <Route path="/interventions/new" element={<CreateInterventionPage />} />
      <Route path="/interventions/:id/edit" element={<CreateInterventionPage />} />
      <Route path="/structure" element={<MappingListPage />} />
      <Route path="/structure/new-vertical" element={<StructureAccessControlPage />} />
      <Route path="/structure/add-lob" element={<AddLobPage />} />
    </Routes>
  );
}
