import { Pipe, PipeTransform } from '@angular/core';

import { environment } from '../../../environments/environment';

// The four transforms in 07-DEPLOYMENT.md's table, and the third hand-written
// copy of them: services/storage.py holds the same strings and nothing compares
// the two. That is the exposure O-10 named when it assigned this pipe to its
// first caller, and it is CONVENTIONS.md's hand-mirrored-constant problem again
// — this time with no compiler watching, unlike 114's swatch map.
//
// `thumbnail` is here for completeness and has no caller: the server sends a
// ready-built thumbnail URL on every item (04-API-SPEC.md line 119), so a client
// that rebuilt it would be deriving a value it was handed. DECISIONS.md 118.
export const TRANSFORMS = {
  thumbnail: 'w_300,h_300,c_pad,b_white,f_auto,q_auto',
  detail: 'w_800,c_limit,f_auto,q_auto',
  vision: 'w_800,c_limit,f_jpg,q_auto',
  lookcard: 'w_400,h_500,c_pad,b_transparent,f_auto,q_auto',
} as const;

export type Transform = keyof typeof TRANSFORMS;

export const DELIVERY_HOST = 'https://res.cloudinary.com';

// encodeURI rather than encodeURIComponent, mirroring the backend's `quote()`:
// a public_id carries folder separators (bijoux/users/<uuid>/<id>) and escaping
// those would ask Cloudinary for a file whose name contains slashes.
export function cloudinaryUrl(publicId: string, transform: Transform): string {
  return `${DELIVERY_HOST}/${environment.cloudinaryCloudName}/image/upload/${TRANSFORMS[transform]}/${encodeURI(publicId)}`;
}

@Pipe({ name: 'cloudinaryUrl' })
export class CloudinaryUrlPipe implements PipeTransform {
  transform(publicId: string, transform: Transform): string {
    return cloudinaryUrl(publicId, transform);
  }
}
