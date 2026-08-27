// frontend/src/app/shared/models/enums.ts
// Hand-mirror of backend/app/enums.py. docs/02-DATA-MODEL.md is authoritative
// for both — add a value there first, then to each mirror.

export const ITEM_STATUSES = ['processing', 'ready', 'failed'] as const;
export type ItemStatus = (typeof ITEM_STATUSES)[number];

// Appended rather than grouped with the garments, for the reason app/enums.py
// gives: migration 0003 added them to the item_category type with ALTER TYPE
// … ADD VALUE, which appends, and the two orders are kept identical.
export const CATEGORIES = [
  'top',
  'bottom',
  'dress',
  'outerwear',
  'shoes',
  'bag',
  'accessory',
  'swimwear',
  'sleepwear',
] as const;
export type Category = (typeof CATEGORIES)[number];

export const LAYERS = ['base', 'mid', 'outer', 'standalone'] as const;
export type Layer = (typeof LAYERS)[number];

export const FITS = [
  'skinny',
  'slim',
  'straight',
  'relaxed',
  'oversized',
  'wide',
  'bodycon',
  'a_line',
  'flowy',
] as const;
export type Fit = (typeof FITS)[number];

export const LENGTHS = [
  'sleeveless',
  'short_sleeve',
  'long_sleeve',
  'crop',
  'regular',
  'longline',
  'mini',
  'midi',
  'maxi',
  'ankle',
  'full',
] as const;
export type Length = (typeof LENGTHS)[number];

export const RISES = ['low', 'mid', 'high'] as const;
export type Rise = (typeof RISES)[number];

export const COLORS = [
  'black',
  'white',
  'grey',
  'beige',
  'brown',
  'navy',
  'blue',
  'light_blue',
  'red',
  'pink',
  'orange',
  'yellow',
  'green',
  'olive',
  'purple',
  'gold',
  'silver',
] as const;
export type Color = (typeof COLORS)[number];

export const PATTERNS = [
  'solid',
  'stripes',
  'checks',
  'floral',
  'animal',
  'graphic',
  'denim_wash',
  'other',
] as const;
export type Pattern = (typeof PATTERNS)[number];

export const MATERIALS = [
  'cotton',
  'denim',
  'knit',
  'wool',
  'leather',
  'linen',
  'silk',
  'synthetic',
  'other',
] as const;
export type Material = (typeof MATERIALS)[number];

// Not an item column — it names the sky. It lives in this mirror because
// `GET /weather` returns it and the strip renders it, and because the reason
// every other list here is closed applies unchanged: one weather, one i18n key.
export const CONDITIONS = [
  'clear',
  'partly_cloudy',
  'cloudy',
  'fog',
  'drizzle',
  'rain',
  'snow',
  'thunderstorm',
] as const;
export type Condition = (typeof CONDITIONS)[number];

// Not an item column either — it names what the user is dressing for, and it
// reached this mirror at task 2.7 from 04-API-SPEC.md by way of 02. Nothing in
// the database refuses a value outside it: `looks.occasion` is TEXT, so the
// request schema on POST /looks/suggest is the whole of the enforcement. The
// chips that render these are 2.8's.
export const OCCASIONS = ['casual', 'work', 'evening', 'sport', 'formal', 'travel'] as const;
export type Occasion = (typeof OCCASIONS)[number];

export const SUBCATEGORIES = {
  top: ['t_shirt', 'tank', 'shirt', 'blouse', 'sweater', 'sweatshirt', 'hoodie', 'bodysuit'],
  bottom: ['jeans', 'trousers', 'shorts', 'skirt', 'leggings', 'cargo'],
  dress: ['dress', 'jumpsuit'],
  outerwear: ['jacket', 'coat', 'blazer', 'cardigan', 'vest', 'puffer'],
  shoes: ['sneakers', 'boots', 'heels', 'flats', 'sandals', 'loafers'],
  bag: ['tote', 'crossbody', 'shoulder', 'clutch', 'backpack'],
  accessory: ['belt', 'scarf', 'hat', 'sunglasses', 'jewelry'],
  swimwear: ['swimsuit', 'bikini', 'swim_shorts', 'cover_up', 'rash_guard'],
  sleepwear: ['pajamas', 'nightdress', 'robe'],
} as const satisfies Record<Category, readonly string[]>;

export type Subcategory = (typeof SUBCATEGORIES)[Category][number];
