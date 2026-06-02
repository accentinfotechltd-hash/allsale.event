# Image testing rules (testing agent reference)

- Always base64-encode for tests; accepted formats: JPEG, PNG, WEBP only.
- Re-detect MIME after any transformation.
- Reject SVG, BMP, HEIC, animated GIF/APNG.
- For animated formats, extract first frame only.
- Resize huge images to reasonable bounds before sending.
- Image must contain real features (no blank/solid-color).
