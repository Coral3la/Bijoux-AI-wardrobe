import { Pipe, PipeTransform } from '@angular/core';

import { environment } from '../../../environments/environment';

// The two rows of 07-DEPLOYMENT.md's table this client names. `detail` is the
// one it builds, for the item screen, and it has no counterpart in
// services/storage.py: the API never builds it. `thumbnail` is the one string
// hand-mirrored from storage.py, and nothing compares the two copies — the
// exposure O-10 named when it assigned this pipe to its first caller, and
// CONVENTIONS.md's hand-mirrored-constant problem again, this time with no
// compiler watching, unlike 114's swatch map.
//
// `thumbnail` is here for completeness and has no caller: the server sends a
// ready-built thumbnail URL on every item (04-API-SPEC.md line 119), so a client
// that rebuilt it would be deriving a value it was handed. DECISIONS.md 118.
export const TRANSFORMS = {
  thumbnail: 'w_300,h_300,c_pad,b_white,f_auto,q_auto',
  detail: 'w_800,c_limit,f_auto,q_auto',
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
