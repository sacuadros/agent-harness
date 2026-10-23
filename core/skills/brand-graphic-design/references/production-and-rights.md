# Production and rights

## Delivery specification

Confirm only what the destination requires:

- pixel or physical dimensions, aspect ratio, orientation, safe area, crop behavior, and bleed;
- RGB/sRGB for typical screens; CMYK and printer-supplied profile only for an actual print workflow;
- raster resolution at final size; vector source for marks, icons, diagrams, and scalable type-heavy artwork;
- format, alpha, compression, maximum file size, naming, versions, and editable source;
- responsive or channel-specific variants rather than blind resizing.

Inspect the exported file, not only the source canvas. Check clipping, missing fonts, substitutions, banding, artifacts, transparent edges, overprint/bleed when relevant, and readability at final size.

## Typography and assets

- Verify font license, weights, language coverage, embedding, and fallback behavior.
- Verify image, illustration, icon, texture, mockup, and template rights and attribution requirements.
- Preserve source and license records for third-party assets.
- Do not claim exclusivity for generated marks or images without legal review.
- Avoid generating recognizable trademarks, copyrighted characters, or a living artist's signature style unless the request and rights clearly permit it.

## AI provenance

Record which assets were generated or materially edited, the tool/path used, source references, and human review. Use [C2PA Content Credentials](https://spec.c2pa.org/specifications/specifications/2.2/specs/C2PA_Specification.html) only when the publication workflow supports and benefits from verifiable provenance; do not make it mandatory for internal drafts.
