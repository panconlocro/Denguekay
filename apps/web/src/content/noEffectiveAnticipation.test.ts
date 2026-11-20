import { describe, expect, it } from 'vitest';
import helpRaw from './help.json?raw';

// The project does not use an "effective anticipation" counted from the emission date: the horizons
// h = 2, 3 and 4 are counted from the cutoff week. No view, helper or help text may bring it back.
const sources = import.meta.glob(
  ['../**/*.ts', '../**/*.tsx', '!../**/*.test.ts', '!../api/schema.d.ts'],
  {
    query: '?raw',
    import: 'default',
    eager: true,
  },
) as Record<string, string>;

const forbidden = [
  /anticipaci[oó]n efectiva/i,
  /semanas efectivas/i,
  /desde la emisi[oó]n/i,
  /minimumWeeks/,
  /effective lead/i,
  /sin anticipaci[oó]n/i,
];

describe('no effective anticipation', () => {
  it('scans the views, helpers and the help content', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
    expect(Object.keys(sources).some((path) => path.endsWith('PublicationNotice.tsx'))).toBe(true);
  });

  it('is not mentioned by any view, helper or help text', () => {
    const all: Record<string, string> = { ...sources, 'content/help.json': helpRaw };
    const hits = Object.entries(all).flatMap(([path, text]) =>
      forbidden.filter((pattern) => pattern.test(text)).map((pattern) => `${path}: ${pattern}`),
    );
    expect(hits).toEqual([]);
  });
});
