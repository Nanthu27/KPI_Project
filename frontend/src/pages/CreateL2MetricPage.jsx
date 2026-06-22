import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import MetricFormPage from '../components/MetricFormPage';
import { useKpiStore } from '../store/kpiStore';
import { l2MetricsApi, interventionsApi } from '../api/client';

export default function CreateL2MetricPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const { verticalHorizontal, lob, interventions, l2Metrics, fetchAll, showToast } = useKpiStore();
  const [initialValues, setInitialValues] = useState(null);
  const [initialDependencies, setInitialDependencies] = useState(null);

  useEffect(() => {
    if (isEdit) {
      const record = l2Metrics.find((m) => String(m.id) === String(id));
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
        const feedingInterventions = interventions
          .filter((iv) => (iv.l2_metrics || []).some((link) => String(link.id) === String(record.id)))
          .map((iv) => {
            const link = iv.l2_metrics.find((lk) => String(lk.id) === String(record.id));
            return { id: iv.id, name: iv.name, impact_factor: link?.impact_factor ?? 0 };
          });
        setInitialDependencies(feedingInterventions);
      }
    }
  }, [isEdit, id, l2Metrics, interventions]);

  // L2 metrics are fed BY Interventions. Each chosen Intervention's own
  // l2_links are updated (intervention.set_l2_links) to point at this L2.
  const dependencyOptions = useMemo(
    () => interventions.map((iv) => ({ id: iv.id, name: iv.name })),
    [interventions]
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
      let l2Id = id;
      if (isEdit) {
        await l2MetricsApi.update(id, payload);
      } else {
        const res = await l2MetricsApi.create(payload);
        l2Id = res.data.id;
      }

      for (const dep of dependencies) {
        const ivRecord = interventions.find((iv) => String(iv.id) === String(dep.id));
        const existingLinks = (ivRecord?.l2_metrics || [])
          .filter((link) => String(link.id) !== String(l2Id))
          .map((link) => ({ l2_metric_id: link.id, impact_factor: link.impact_factor }));
        await interventionsApi.update(dep.id, {
          l2_links: [...existingLinks, { l2_metric_id: l2Id, impact_factor: dep.impact_factor }],
        });
      }

      await fetchAll();
      showToast(isEdit ? 'L2 Metric updated' : 'L2 Metric created');
      navigate('/');
    } catch (e) {
      console.error(e);
      showToast('Failed to save L2 Metric', 'error');
    }
  };

  return (
    <MetricFormPage
      entityLabel="L2 Metrics"
      nameFieldLabel="L2 Name"
      hasDependencies
      dependencyLabel="from intervention"
      dependencyOptionLabel="Intervention Name"
      dependencyOptions={dependencyOptions}
      dependencyTableHeaders={['L2 Metrics', 'Intervention']}
      initialValues={initialValues}
      initialDependencies={initialDependencies}
      verticalHorizontal={verticalHorizontal}
      lob={lob}
      onSave={handleSave}
      onBack={() => navigate('/')}
    />
  );
}
