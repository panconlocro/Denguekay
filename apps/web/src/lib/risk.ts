import type { RiskLevel } from '../api/types';

export const riskColors: Record<RiskLevel | 'missing', string> = {
  bajo: '#3f9a62',
  medio: '#d9a92e',
  alto: '#dd7330',
  muy_alto: '#b3312e',
  missing: '#a5abb2',
};
