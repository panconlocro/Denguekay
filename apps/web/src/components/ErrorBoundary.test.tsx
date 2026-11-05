import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

it('shows recovery instead of a blank page when a view cannot load', () => {
  const log = vi.spyOn(console, 'error').mockImplementation(() => {});
  function BrokenView() {
    throw new Error('chunk unavailable');
    return null;
  }
  try {
    render(
      <ErrorBoundary>
        <BrokenView />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Recargar aplicación' })).toBeVisible();
  } finally {
    log.mockRestore();
  }
});
