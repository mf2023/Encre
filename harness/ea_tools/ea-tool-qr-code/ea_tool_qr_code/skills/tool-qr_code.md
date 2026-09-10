---
name: tool-qr_code
description: "Generate QR codes as PNG/SVG images, or decode QR codes and barcodes from an existing image. Use `generate` for raster PNG/JPG/BMP output, `generate_svg` for scalable vector output, and `read` to extract a payload from a scanned code. Do NOT use this for general image conversion (use image), for generating data charts (use chart), or for AI image synthesis (use generate_image). Tips: raise `error_correction` (L<M<Q<H) to keep codes scannable when printed small or partially obscured; pick colors with strong contrast. Pitfalls: decoding requires pyzbar plus the system zbar library \u9225?if missing, `read` returns an install hint rather than a payload."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# qr_code

Generate QR codes as PNG/SVG images, or decode QR codes and barcodes from an existing image. Use `generate` for raster PNG/JPG/BMP output, `generate_svg` for scalable vector output, and `read` to extract a payload from a scanned code. Do NOT use this for general image conversion (use image), for generating data charts (use chart), or for AI image synthesis (use generate_image). Tips: raise `error_correction` (L<M<Q<H) to keep codes scannable when printed small or partially obscured; pick colors with strong contrast. Pitfalls: decoding requires pyzbar plus the system zbar library 鈥?if missing, `read` returns an install hint rather than a payload.
