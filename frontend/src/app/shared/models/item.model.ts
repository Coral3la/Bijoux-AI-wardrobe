import { Category, Color, ItemStatus, Layer, Material, Pattern } from './enums';

// Mirrors ItemResponse in backend/app/schemas/item.py field for field, and
// keeps the server's snake_case (DECISIONS.md 059). The typing follows the
// backend's own gradient rather than tightening it: the six fields below that
// carry a union are PostgreSQL enum types, while subcategory, fit, length and
// rise are TEXT validated at write time by validate_tag_dict (DECISIONS.md
// 023). A union on those four would claim a guarantee the wire does not make.
export interface Item {
  readonly id: string;
  readonly short_id: string;
  readonly status: ItemStatus;
  readonly image_public_id: string;
  readonly image_url: string;

  readonly category: Category | null;
  readonly subcategory: string | null;
  readonly fit: string | null;
  readonly length: string | null;
  readonly rise: string | null;
  readonly color_primary: Color | null;
  readonly color_secondary: Color | null;
  readonly pattern: Pattern | null;
  readonly material: Material | null;
  readonly formality: number | null;
  readonly warmth: number | null;
  readonly layer: Layer | null;
  // The one tag that is not nullable: the column is NOT NULL DEFAULT FALSE, so
  // on a processing row this reads as "not water resistant" rather than
  // "unknown". Found by the 2026-08-18 audit as F-5.
  readonly water_resistant: boolean;

  readonly display_name: string | null;
  readonly attributes: Record<string, unknown>;
  readonly ai_confidence: number | null;
  readonly user_edited: boolean;
  readonly error_message: string | null;
  readonly is_archived: boolean;

  readonly created_at: string;
  readonly updated_at: string;
}

export interface ItemListResponse {
  readonly items: readonly Item[];
  readonly total: number;
}
