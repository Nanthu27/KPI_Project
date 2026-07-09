/**
 * Unit tests for the ImprovementIndicator arrow + color logic.
 *
 * Run: npm test  (Jest + React Testing Library)
 */
import { render, screen } from '@testing-library/react';
import ImprovementIndicator from '../components/ImprovementIndicator';

const COLORS = {
  accentGreen: '#2ECC71',
  accentRed: '#E15554',
  textMuted: '#9492A8',
};

function renderIndicator(props) {
  return render(<ImprovementIndicator {...props} />);
}

describe('ImprovementIndicator — arrow direction', () => {
  test('shows Up arrow when currentValue > savedValue', () => {
    renderIndicator({ currentValue: 50, savedValue: 40, higherIsBetter: true });
    expect(screen.getByTestId('ArrowUpwardIcon')).toBeTruthy();
  });

  test('shows Down arrow when currentValue < savedValue', () => {
    renderIndicator({ currentValue: 30, savedValue: 40, higherIsBetter: true });
    expect(screen.getByTestId('ArrowDownwardIcon')).toBeTruthy();
  });
});

describe('ImprovementIndicator — color logic', () => {
  test('Higher the Better + Increased → Green', () => {
    renderIndicator({ currentValue: 50, savedValue: 40, higherIsBetter: true });
    const icon = screen.getByTestId('ArrowUpwardIcon');
    expect(icon).toHaveStyle(`color: ${COLORS.accentGreen}`);
  });

  test('Higher the Better + Decreased → Red', () => {
    renderIndicator({ currentValue: 30, savedValue: 40, higherIsBetter: true });
    const icon = screen.getByTestId('ArrowDownwardIcon');
    expect(icon).toHaveStyle(`color: ${COLORS.accentRed}`);
  });

  test('Lower the Better + Increased → Red', () => {
    renderIndicator({ currentValue: 50, savedValue: 40, higherIsBetter: false });
    const icon = screen.getByTestId('ArrowUpwardIcon');
    expect(icon).toHaveStyle(`color: ${COLORS.accentRed}`);
  });

  test('Lower the Better + Decreased → Green', () => {
    renderIndicator({ currentValue: 30, savedValue: 40, higherIsBetter: false });
    const icon = screen.getByTestId('ArrowDownwardIcon');
    expect(icon).toHaveStyle(`color: ${COLORS.accentGreen}`);
  });

  test('No change → neutral color', () => {
    renderIndicator({ currentValue: 40, savedValue: 40, higherIsBetter: true });
    const icon = screen.getByTestId('ArrowDownwardIcon');
    expect(icon).toHaveStyle(`color: ${COLORS.textMuted}`);
  });
});

describe('ImprovementIndicator — change % display', () => {
  test('shows correct % when value increases by 25%', () => {
    renderIndicator({ currentValue: 50, savedValue: 40, higherIsBetter: true, unit: '%' });
    expect(screen.getByText(/25\.0%/)).toBeTruthy();
  });

  test('shows absolute value (no negative sign)', () => {
    renderIndicator({ currentValue: 30, savedValue: 40, higherIsBetter: true, unit: '%' });
    // Should show 25.0% not -25.0%
    expect(screen.getByText(/25\.0%/)).toBeTruthy();
    expect(screen.queryByText(/-/)).toBeNull();
  });
});
