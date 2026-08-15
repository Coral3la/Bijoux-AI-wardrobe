import { describe, expect, it } from 'vitest';

import { User, userLabel } from './user.model';

function user(display_name: string | null): User {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'coral@example.com',
    display_name,
    height_cm: null,
    size_top: null,
    size_bottom: null,
    size_shoe: null,
    style_notes: null,
    home_city: null,
    home_lat: null,
    home_lon: null,
    created_at: '2026-08-11T09:00:00Z',
  };
}

describe('userLabel', () => {
  it('uses the display name when there is one', () => {
    expect(userLabel(user('Coral'))).toBe('Coral');
  });

  it('falls back to the email when the display name is null', () => {
    expect(userLabel(user(null))).toBe('coral@example.com');
  });

  it('falls back when the display name is an empty string', () => {
    expect(userLabel(user(''))).toBe('coral@example.com');
  });

  it('falls back when the display name is only whitespace', () => {
    expect(userLabel(user('   '))).toBe('coral@example.com');
  });

  // Not about typography, which no unit test can assert: this pins the function
  // as script-agnostic, so a later normalise() or slug step fails here first.
  it('returns a non-Latin display name unchanged', () => {
    expect(userLabel(user('קורל'))).toBe('קורל');
  });
});
