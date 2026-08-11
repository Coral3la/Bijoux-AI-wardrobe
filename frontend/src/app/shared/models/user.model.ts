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

export interface TokenResponse {
  readonly access_token: string;
  readonly token_type: 'bearer';
  readonly user: User;
}
