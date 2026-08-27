import { Condition } from './enums';

// Mirrors the 200 of `GET /weather` in 04-API-SPEC.md field for field, keeping
// the server's snake_case (DECISIONS.md 059). `condition` carries a union
// because it is the closed vocabulary in 02-DATA-MODEL.md, mapped from
// Open-Meteo's WMO code server-side — the same gradient item.model.ts follows.
//
// `rule` is the exact string the stylist prompt receives. It is on the wire to
// make the system inspectable and is deliberately not rendered: it is written
// for a model, not for a person.
export interface Weather {
  readonly date: string;
  readonly temp_min_c: number;
  readonly temp_max_c: number;
  readonly precip_mm: number;
  readonly wind_kph: number;
  readonly condition: Condition;
  readonly rule: string;
}
