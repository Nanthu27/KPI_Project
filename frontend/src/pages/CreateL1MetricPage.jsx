import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import MetricFormPage from '../components/MetricFormPage';
import { useKpiStore } from '../store/kpiStore';
import { l1MetricsApi, l2MetricsApi } from '../api/client';

export default function CreateL1MetricPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const { verticalHorizontal, lob, l2Metrics, l1Metrics, fetchAll, showToast } = useKpiStore();
  const [initialValues, setInitialValues] = useState(null);
  const [initialDependencies, setInitialDependencies] = useState(null);

  useEffect(() => {
    if (isEdit) {
      const record = l1Metrics.find((m) => String(m.id) === String(id));
      if (record) {
        setInitialValues({
          name: record.name,
          unit: record.unit,
          default_value: record.default_value,
          min_value: record.min_value,
          max_value: record.max_value,
          band_min: record.band_min,
          target_value: record.target_value,
          metric_direction: record.higher_is_better ? 'higher_is_better' : 'lower_is_better',
        });
        // Which L2 metrics currently declare this L1 as a target (l2.l1_metrics includes this L1's id)
        const feedingL2s = l2Metrics
          .filter((l2) => (l2.l1_metrics || []).some((link) => String(link.id) === String(record.id)))
          .map((l2) => {
            const link = l2.l1_metrics.find((lk) => String(lk.id) === String(record.id));
            return { id: l2.id, name: l2.name, impact_factor: link?.impact_factor ?? 0 };
          });
        setInitialDependencies(feedingL2s);
      }
    }
  }, [isEdit, id, l1Metrics, l2Metrics]);

  // L1 metrics are fed BY L2 metrics. The dependency picker lets the user
  // choose which L2 metrics feed into this L1 (and at what impact factor),
  // mirroring the "Dependencies (from L2 Metrics)" screen. Internally, each
  // chosen L2 metric's own outgoing links (l2.set_l1_links) are updated to
  // point at this L1, since the L2->L1 edge is stored on the L2 side.
  const dependencyOptions = useMemo(
    () => l2Metrics.map((m) => ({ id: m.id, name: m.name })),
    [l2Metrics]
  );

  const handleSave = async (values, dependencies) => {
    const payload = {
      name: values.name,
      unit: values.unit || '%',
      default_value: Number(values.default_value) || 0,
      min_value: Number(values.min_value) || 0,
      max_value: Number(values.max_value) || 100,
      band_min: Number(values.band_min) || 0,
      target_value: Number(values.target_value) || 0,
      higher_is_better: values.metric_direction === 'higher_is_better',
      vertical_horizontal: verticalHorizontal,
      lob,
    };

    try {
      let l1Id = id;
      if (isEdit) {
        await l1MetricsApi.update(id, payload);
      } else {
        const res = await l1MetricsApi.create(payload);
        l1Id = res.data.id;
      }

      // For each L2 metric chosen as a dependency, update ITS l1_links to
      // include (or update) an edge pointing at this L1 with the given
      // impact factor, preserving any of that L2's other existing edges.
      for (const dep of dependencies) {
        const l2Record = l2Metrics.find((m) => String(m.id) === String(dep.id));
        const existingLinks = (l2Record?.l1_metrics || [])
          .filter((link) => String(link.id) !== String(l1Id))
          .map((link) => ({ l1_metric_id: link.id, impact_factor: link.impact_factor }));
        await l2MetricsApi.update(dep.id, {
          l1_links: [...existingLinks, { l1_metric_id: l1Id, impact_factor: dep.impact_factor }],
        });
      }

      await fetchAll();
      showToast(isEdit ? 'L1 Metric updated' : 'L1 Metric created');
      navigate('/');
    } catch (e) {
      console.error(e);
      showToast('Failed to save L1 Metric', 'error');
    }
  };

  return (
    <MetricFormPage
      entityLabel="L1 Metrics"
      nameFieldLabel="L1 Name"
      hasDependencies
      dependencyLabel="from L2 Metrics"
      dependencyOptionLabel="L2 Name"
      dependencyOptions={dependencyOptions}
      dependencyTableHeaders={['L1 Metrics', 'L2 Metrics']}
      initialValues={initialValues}
      initialDependencies={initialDependencies}
      verticalHorizontal={verticalHorizontal}
      lob={lob}
      onSave={handleSave}
      onBack={() => navigate('/')}
    />
  );
}
