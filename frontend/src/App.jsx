import { useEffect, useRef, useState } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import { Box, Snackbar, Alert, CircularProgress, Typography } from '@mui/material';

import Header from './components/Header';
import FilterBar from './components/FilterBar';
import KPIColumn from './components/KPIColumn';
import KPICard from './components/KPICard';
import InterventionCard from './components/InterventionCard';
import ConfirmDeleteDialog from './components/ConfirmDeleteDialog';
import UserGuidePopover from './components/UserGuidePopover';
import AiPanel from './components/AiPanel';
import CreateL1MetricPage from './pages/CreateL1MetricPage';
import CreateL2MetricPage from './pages/CreateL2MetricPage';
import CreateBusinessOutcomePage from './pages/CreateBusinessOutcomePage';
import CreateInterventionPage from './pages/CreateInterventionPage';
import StructureAccessControlPage from './pages/StructureAccessControlPage';
import { useKpiStore, COLUMN_KEYS } from './store/kpiStore';
import { useAiPanelStore } from './store/aiPanelStore';
import { COLORS } from './theme/theme';

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
    businessOutcomes, l1Metrics, l2Metrics, interventions,
    loading, error, toast,
    expandedColumns, toggleColumn,
    loadFilterOptions, setVerticalHorizontal, setLob, fetchAll,
    deleteRecord, updateInterventionValue,
    clearToast,
  } = useKpiStore();

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const userGuideButtonRef = useRef(null);

  const { panelOpen: aiPanelOpen, togglePanel: toggleAiPanel, openPanel: openAiPanel } = useAiPanelStore();

  const handleApplyToSliders = async (agentData) => {
    // Goal-Seeking plan items and Decision Advisor's recommended option both
    // resolve to a list of {name, value} pairs; match by intervention name
    // (case-insensitive) against the live interventions list and push each
    // value through the existing updateInterventionValue action, which
    // already PUTs to the backend and re-fetches the cascade.
    const planItems = agentData.plan?.map((p) => ({ name: p.intervention, value: p.recommended_value })) ||
      agentData.all_options?.find((o) => o.label === agentData.recommended_option)?.interventions || [];

    for (const item of planItems) {
      const match = interventions.find((iv) => iv.name.toLowerCase() === item.name.toLowerCase());
      if (match) {
        await updateInterventionValue(match.id, item.value);
      }
    }
  };

  useEffect(() => {
    (async () => {
      await loadFilterOptions();
      await fetchAll();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dataByColumn = {
    [COLUMN_KEYS.BUSINESS_OUTCOMES]: businessOutcomes,
    [COLUMN_KEYS.L1_METRICS]: l1Metrics,
    [COLUMN_KEYS.L2_METRICS]: l2Metrics,
    [COLUMN_KEYS.INTERVENTIONS]: interventions,
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    await deleteRecord(deleteTarget.column, deleteTarget.record.id);
    setDeleteTarget(null);
  };

  return (
    <>
      <Box sx={{ minHeight: '100vh', backgroundColor: '#3A3950', p: 2, display: 'flex', justifyContent: 'center' }}>
        <Box sx={{ display: 'flex', width: '100%', maxWidth: 1880, boxShadow: '0 10px 40px rgba(0,0,0,0.3)', borderRadius: '4px', overflow: 'hidden' }}>
          <Box sx={{ flex: 1, minWidth: 0, backgroundColor: COLORS.background, display: 'flex', flexDirection: 'column' }}>
            <Header
              onUploadExcel={(file) => useKpiStore.getState().uploadExcelFile(file)}
              onToggleAiPanel={() => (aiPanelOpen ? toggleAiPanel() : openAiPanel())}
              aiPanelOpen={aiPanelOpen}
            />
            <FilterBar
              verticalHorizontal={verticalHorizontal}
              lob={lob}
              verticalOptions={verticalOptions}
              lobOptions={lobOptions}
              onChangeVertical={setVerticalHorizontal}
              onChangeLob={setLob}
              onStructureClick={() => navigate('/structure')}
              onUserGuideClick={() => setGuideOpen(true)}
              userGuideButtonRef={userGuideButtonRef}
            />
            <Box sx={{ position: 'relative', flex: 1, minHeight: 560 }}>
              {loading && (
                <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(236,236,236,0.6)', zIndex: 10 }}>
                  <CircularProgress sx={{ color: COLORS.primary }} />
                </Box>
              )}
              {error && <Box sx={{ p: 4 }}><Typography color="error">{error}</Typography></Box>}
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 2, p: 2, height: 620 }}>
                {COLUMN_CONFIG.map(({ key, title, isFirstColumn, createPath, editPath }) => (
                  <KPIColumn
                    key={key}
                    title={title}
                    column={key}
                    isFirstColumn={isFirstColumn}
                    expanded={expandedColumns[key]}
                    onToggleExpand={() => toggleColumn(key)}
                    onAddClick={() => navigate(createPath)}
                  >
                    {dataByColumn[key].map((record) =>
                      key === COLUMN_KEYS.INTERVENTIONS ? (
                        <InterventionCard
                          key={record.id}
                          record={record}
                          onEdit={(r) => navigate(editPath(r.id))}
                          onDelete={(r) => setDeleteTarget({ column: key, record: r })}
                          onChangeValue={(id, v) =>
                            useKpiStore.setState((state) => ({
                              interventions: state.interventions.map((iv) =>
                                iv.id === id ? { ...iv, percentage: v } : iv
                              ),
                            }))
                          }
                          onCommitValue={(id, v) => updateInterventionValue(id, v)}
                        />
                      ) : (
                        <KPICard
                          key={record.id}
                          record={record}
                          onEdit={(r) => navigate(editPath(r.id))}
                          onDelete={(r) => setDeleteTarget({ column: key, record: r })}
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

          {aiPanelOpen && (
            <AiPanel
              verticalHorizontal={verticalHorizontal}
              lob={lob}
              onApplyToSliders={handleApplyToSliders}
            />
          )}
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
    </>
  );
}

export default function App() {
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
      <Route path="/structure" element={<StructureAccessControlPage />} />
    </Routes>
  );
}
