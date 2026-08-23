import { describe, expect, it } from 'vitest';

import { environment } from '../../../environments/environment';
import { CloudinaryUrlPipe, TRANSFORMS, cloudinaryUrl } from './cloudinary-url.pipe';

describe('cloudinaryUrl', () => {
  // Transcribed by hand from 07-DEPLOYMENT.md's transform table, never read
  // from TRANSFORMS. 101 is the reason: at 1.6 every expectation about
  // MAX_UPLOAD_BYTES was written in terms of the constant it was testing, so
  // mutating the constant moved the goalposts and 155 tests stayed green.
  it('builds the detail transform from 07s table', () => {
    expect(cloudinaryUrl('bijoux/users/1/abc', 'detail')).toBe(
      `https://res.cloudinary.com/${environment.cloudinaryCloudName}/image/upload/w_800,c_limit,f_auto,q_auto/bijoux/users/1/abc`,
    );
  });

  it('builds the thumbnail transform the server also builds', () => {
    expect(cloudinaryUrl('bijoux/users/1/abc', 'thumbnail')).toBe(
      `https://res.cloudinary.com/${environment.cloudinaryCloudName}/image/upload/w_300,h_300,c_pad,b_white,f_auto,q_auto/bijoux/users/1/abc`,
    );
  });

  // The four strings pinned individually, against the document rather than
  // against themselves. Mutating any one of them fails exactly one row.
  it('carries 07s four transforms verbatim', () => {
    expect(TRANSFORMS).toEqual({
      thumbnail: 'w_300,h_300,c_pad,b_white,f_auto,q_auto',
      detail: 'w_800,c_limit,f_auto,q_auto',
      vision: 'w_800,c_limit,f_jpg,q_auto',
      lookcard: 'w_400,h_500,c_pad,b_transparent,f_auto,q_auto',
    });
  });

  // The backend uses quote(), which leaves "/" alone for exactly this reason.
  it('keeps folder separators and escapes what would change the path', () => {
    expect(cloudinaryUrl('bijoux/users/1/a b', 'detail')).toContain('/bijoux/users/1/a%20b');
  });

  it('is the same function through the pipe', () => {
    expect(new CloudinaryUrlPipe().transform('bijoux/users/1/abc', 'detail')).toBe(
      cloudinaryUrl('bijoux/users/1/abc', 'detail'),
    );
  });
});
