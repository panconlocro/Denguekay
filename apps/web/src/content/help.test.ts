import { describe, expect, it } from 'vitest';
import content from './help.json';

const text = JSON.stringify(content);

describe('help and manual content', () => {
  it('describes the current V4 model and no longer refers to the v2', () => {
    expect(text).toContain('La V4 se sirve hoy como selección experimental');
    expect(text).not.toMatch(/\bv2\b/i);
    expect(text).not.toContain('[canal de soporte por confirmar]');
  });

  it('lists the four risk levels with their thresholds and the no-data state', () => {
    const risk = content.topics.find((topic) => topic.id === 'riesgo')!;
    const body = risk.paragraphs.join(' ');
    for (const level of [
      'Bajo: probabilidad menor que 0,25',
      'Medio: desde 0,25 y menor que 0,50',
      'Alto: desde 0,50 y menor que 0,75',
      'Muy alto: 0,75 o más',
      'Sin datos indica que no hay una predicción válida',
    ])
      expect(body).toContain(level);
  });

  it('covers every concept of the user stories HU0017-1 to HU0017-3', () => {
    const topics = new Map(content.topics.map((topic) => [topic.id, topic]));
    for (const id of [
      'filtros',
      'tablero',
      'series',
      'mapa',
      'avisos',
      'tiempo',
      'resultados',
      'datos',
    ])
      expect(topics.has(id), id).toBe(true);
    expect(topics.get('tablero')!.paragraphs.join(' ')).toContain('alcance regional');
    expect(topics.get('mapa')!.paragraphs.join(' ')).toContain(
      'Instituto Geográfico Nacional (IGN)',
    );
    expect(topics.get('mapa')!.paragraphs.join(' ')).toContain('CC BY-IGO 3.0');
    const time = topics.get('tiempo')!.paragraphs.join(' ');
    for (const word of ['semana de corte', 'semana objetivo', 'fecha de actualización'])
      expect(time).toContain(word);
    expect(topics.get('experimental')!.paragraphs.join(' ')).toContain('Validado significa');
    expect(topics.get('datos')!.paragraphs.join(' ')).toContain('Causas posibles');
    expect(topics.get('datos')!.steps.length).toBeGreaterThan(0);
  });

  it('gives the support contacts and every page of the manual has topics', () => {
    expect(content.support.contacts).toEqual([
      { name: 'Rosa Rodríguez', email: 'rosamariarv10@gmail.com' },
      { name: 'Nicolás Miranda', email: 'turppie24@gmail.com' },
    ]);
    const pages = new Set(content.topics.map((topic) => topic.page));
    expect([...pages].sort()).toEqual(content.manual.pages.map((_, index) => index + 1));
  });
});
