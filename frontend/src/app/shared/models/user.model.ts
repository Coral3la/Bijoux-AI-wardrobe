export interface User {
  readonly id: string;
  readonly email: string;
  readonly display_name: string | null;
  readonly height_cm: number | null;
  readonly size_top: string | null;
  readonly size_bottom: string | null;
  readonly size_shoe: string | null;
  readonly style_notes: string | null;
  readonly home_city: string | null;
  readonly home_lat: number | null;
  readonly home_lon: number | null;
  readonly created_at: string;
}

// The body of `PATCH /me`, and every field is optional for the reason
// `ItemUpdate`'s are: the endpoint reads `exclude_unset`, so an omitted key is
// left alone where an explicit null clears the column. 04-API-SPEC.md.
//
// The three home fields are one field in three columns (DECISIONS.md 151) —
// supplied together or cleared together, and any other combination is a 422.
// Nothing should build this object a home field at a time.
export interface UserUpdate {
  readonly display_name?: string | null;
  readonly height_cm?: number | null;
  readonly size_top?: string | null;
  readonly size_bottom?: string | null;
  readonly size_shoe?: string | null;
  readonly style_notes?: string | null;
  readonly home_city?: string | null;
  readonly home_lat?: number | null;
  readonly home_lon?: number | null;
}

export interface TokenResponse {
  readonly access_token: string;
  readonly token_type: 'bearer';
  readonly user: User;
}

// Trimmed rather than `??`: display_name is nullable in the column and the API
// accepts whitespace, so an empty or blank name must fall through to the email
// instead of rendering as nothing. DECISIONS.md 071.
export function userLabel(user: User): string {
  return user.display_name?.trim() || user.email;
}
