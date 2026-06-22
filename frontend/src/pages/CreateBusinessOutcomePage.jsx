import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import MetricFormPage from '../components/MetricFormPage';
import { useKpiStore } from '../store/kpiStore';
import { businessOutcomesApi, l1MetricsApi } from '../api/client';

export default function CreateBusinessOutcomePage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const { verticalHorizontal, lob, l1Metrics, businessOutcomes, fetchAll, showToast } = useKpiStore();
  const [initialValues, setInitialValues] = useState(null);
  const [initialDependencies, setInitialDependencies] = useState(null);

  useEffect(() => {
    if (isEdit) {
      const record = businessOutcomes.find((m) => String(m.id) === String(id));
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
        const feedingL1s = l1Metrics
          .filter((l1) => (l1.business_outcomes || []).some((link) => String(link.id) === String(record.id)))
          .map((l1) => {
            const link = l1.business_outcomes.find((lk) => String(lk.id) === String(record.id));
            return { id: l1.id, name: l1.name, impact_factor: link?.impact_factor ?? 0 };
          });
        setInitialDependencies(feedingL1s);
      }
    }
  }, [isEdit, id, businessOutcomes, l1Metrics]);

  // Business Outcomes are fed BY L1 metrics. Each chosen L1's own
  // business_outcome_links are updated to point at this Business Outcome.
  const dependencyOptions = useMemo(
    () => l1Metrics.map((m) => ({ id: m.id, name: m.name })),
    [l1Metrics]
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
      let boId = id;
      if (isEdit) {
        await businessOutcomesApi.update(id, payload);
      } else {
        const res = await businessOutcomesApi.create(payload);
        boId = res.data.id;
      }

      for (const dep of dependencies) {
        const l1Record = l1Metrics.find((m) => String(m.id) === String(dep.id));
        const existingLinks = (l1Record?.business_outcomes || [])
          .filter((link) => String(link.id) !== String(boId))
          .map((link) => ({ business_outcome_id: link.id, impact_factor: link.impact_factor }));
        await l1MetricsApi.update(dep.id, {
          business_outcome_links: [...existingLinks, { business_outcome_id: boId, impact_factor: dep.impact_factor }],
        });
      }

      await fetchAll();
      showToast(isEdit ? 'Business Outcome updated' : 'Business Outcome created');
      navigate('/');
    } catch (e) {
      console.error(e);
      showToast('Failed to save Business Outcome', 'error');
    }
  };

  return (
    <MetricFormPage
      entityLabel="Business Outcome"
      nameFieldLabel="L0 Name"
      hasDependencies
      dependencyLabel="from L1 Metrics"
      dependencyOptionLabel="L1 Name"
      dependencyOptions={dependencyOptions}
      dependencyTableHeaders={['L0 Metrics', 'L1 Metrics']}
      initialValues={initialValues}
      initialDependencies={initialDependencies}
      verticalHorizontal={verticalHorizontal}
      lob={lob}
      onSave={handleSave}
      onBack={() => navigate('/')}
    />
  );
}
