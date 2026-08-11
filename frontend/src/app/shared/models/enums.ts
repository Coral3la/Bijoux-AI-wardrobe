// frontend/src/app/shared/models/enums.ts
// Hand-mirror of backend/app/enums.py. docs/02-DATA-MODEL.md is authoritative
// for both — add a value there first, then to each mirror.

export const ITEM_STATUSES = ['processing', 'ready', 'failed'] as const;
export type ItemStatus = (typeof ITEM_STATUSES)[number];

export const CATEGORIES = [
  'top',
  'bottom',
  'dress',
  'outerwear',
  'shoes',
  'bag',
  'accessory',
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

export const SUBCATEGORIES = {
  top: ['t_shirt', 'tank', 'shirt', 'blouse', 'sweater', 'sweatshirt', 'hoodie', 'bodysuit'],
  bottom: ['jeans', 'trousers', 'shorts', 'skirt', 'leggings', 'cargo'],
  dress: ['dress', 'jumpsuit'],
  outerwear: ['jacket', 'coat', 'blazer', 'cardigan', 'vest', 'puffer'],
  shoes: ['sneakers', 'boots', 'heels', 'flats', 'sandals', 'loafers'],
  bag: ['tote', 'crossbody', 'shoulder', 'clutch', 'backpack'],
  accessory: ['belt', 'scarf', 'hat', 'sunglasses', 'jewelry'],
} as const satisfies Record<Category, readonly string[]>;

export type Subcategory = (typeof SUBCATEGORIES)[Category][number];
