/**
 * Unit tests for the simulation cascade formulas.
 * These mirror the Python simulation_service.py logic in pure JS so they
 * can be run client-side without a backend.
 *
 * Formula reference (from Excel reverse-engineering):
 *   Intervention → L2:
 *     change%  = (impactFactor * (interventionPct / 100)) / 100
 *     newValue = default * (1 + totalChange%)
 *
 *   L2 → L1:
 *     change%  = impactFactor * l2TotalChange%
 *     newValue = default * (1 + totalChange%)
 *
 *   L1 → BO:
 *     change%  = impactFactor * l1TotalChange%
 *     newValue = default * (1 + totalChange%)
 */

// Pure JS port of the cascade
function interventionToL2(impactFactor, interventionPct) {
  return (impactFactor * (interventionPct / 100)) / 100;
}

function chainChange(impactFactor, upstreamChangePct) {
  return impactFactor * upstreamChangePct;
}

function newValue(defaultValue, totalChangePct) {
  return defaultValue + defaultValue * totalChangePct;
}

describe('Intervention → L2 formula', () => {
  test('slider 10%, impact 10 gives 1% decimal change', () => {
    expect(interventionToL2(10, 10)).toBeCloseTo(0.01);
  });

  test('zero intervention → zero change', () => {
    expect(interventionToL2(0.9, 0)).toBe(0);
  });

  test('multiple interventions sum correctly', () => {
    const change1 = interventionToL2(10, 10); // 1%
    const change2 = interventionToL2(8, 10);  // 0.8%
    expect(change1 + change2).toBeCloseTo(0.018);
  });
});

describe('L2 → L1 formula', () => {
  test('impact 0.9, L2 change 1% → L1 change 0.9%', () => {
    expect(chainChange(0.9, 0.01)).toBeCloseTo(0.009);
  });
});

describe('L1 → Business Outcome formula', () => {
  test('impact 0.7, L1 change 0.9% → BO change 0.63%', () => {
    expect(chainChange(0.7, 0.009)).toBeCloseTo(0.0063);
  });
});

describe('New value calculation', () => {
  test('default 60, 0.63% change → 60.378', () => {
    expect(newValue(60, 0.0063)).toBeCloseTo(60.378, 2);
  });

  test('default 70, 1% change → 70.7', () => {
    expect(newValue(70, 0.01)).toBeCloseTo(70.7, 2);
  });

  test('zero change → returns default unchanged', () => {
    expect(newValue(100, 0)).toBe(100);
  });
});

describe('Full cascade example (from BRD doc)', () => {
  test('IDP 10% → L2 70 → L1 60 → BO 60', () => {
    // Step 1: Intervention
    const l2Change = interventionToL2(10, 10); // 1%
    const l2New = newValue(70, l2Change);
    expect(l2New).toBeCloseTo(70.7, 1);

    // Step 2: L1
    const l1Change = chainChange(0.9, l2Change); // 0.9%
    const l1New = newValue(60, l1Change);
    expect(l1New).toBeCloseTo(60.54, 1);

    // Step 3: BO
    const boChange = chainChange(0.7, l1Change); // 0.63%
    const boNew = newValue(60, boChange);
    expect(boNew).toBeCloseTo(60.378, 2);
  });

  test('supplied Excel example: interventions 17, 11, 11, 0', () => {
    const l2_1_change = interventionToL2(10, 17)
      + interventionToL2(12, 11)
      + interventionToL2(12, 11);
    const l2_2_change = interventionToL2(8, 11) + interventionToL2(20, 11);
    const l2_3_change = interventionToL2(25, 11);

    expect(newValue(24, l2_1_change)).toBeCloseTo(25.0416, 4);
    expect(newValue(35, l2_2_change)).toBeCloseTo(36.078, 3);
    expect(newValue(45, l2_3_change)).toBeCloseTo(46.2375, 4);

    const l1_1_change = (0.7 * l2_1_change) + (0.8 * l2_2_change) + (-0.5 * l2_3_change);
    const l1_2_change = 0.6 * l2_3_change;
    expect(newValue(40, l1_1_change)).toBeCloseTo(41.6508, 4);
    expect(newValue(80, l1_2_change)).toBeCloseTo(81.32, 2);

    const boChange = (-0.35 * l1_1_change) + (-0.55 * l1_2_change);
    expect(newValue(100, boChange)).toBeCloseTo(97.64805, 5);
  });
});
