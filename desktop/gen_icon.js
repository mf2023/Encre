/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * You may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * DISCLAIMER: Users must comply with applicable AI regulations.
 * Non-compliance may result in service termination or legal liability.
 */

/**
 * Generates the Encre tray icon as a PNG at runtime.
 *
 * There is no bundled icon asset; instead a small 16x16 green briefcase is
 * defined pixel-by-pixel, encoded as raw RGBA scanlines, zlib-compressed into
 * an IDAT chunk, wrapped in a minimal valid PNG (signature + IHDR/IDAT/IEND
 * with correct CRC32s) and written to `tray-icon.png` next to this script.
 * This keeps the build dependency-free for the tray artwork.
 */

const zlib = require("zlib");
const fs = require("fs");
const path = require("path");

// Icon dimensions.
const W = 16, H = 16;
// Opaque green color (RGBA) used for the briefcase pixels.
const G = [34, 197, 94, 255];
// Fully transparent color.
const T = [0, 0, 0, 0];

// 1 = green pixel, 0 = transparent. Sketch of a briefcase shape.
const pixels = [
  [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
  [0,0,0,0,1,1,1,1,1,1,0,0,0,0,0,0],
  [0,0,0,0,1,0,0,0,0,1,0,0,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
];

// Build the raw image buffer: each row is a filter byte (0) followed by
// W*4 RGBA bytes, top-to-bottom.
const raw = Buffer.alloc(H * (1 + W * 4));
// Encode the pixel grid into the raw buffer, writing the filter byte then RGBA.
for (let y = 0; y < H; y++) {
  const offset = y * (1 + W * 4);
  raw[offset] = 0;
  for (let x = 0; x < W; x++) {
    const isGreen = pixels[y][x];
    const color = isGreen ? G : T;
    const po = offset + 1 + x * 4;
    raw[po] = color[0];
    raw[po + 1] = color[1];
    raw[po + 2] = color[2];
    raw[po + 3] = color[3];
  }
}

// Compress the raw scanlines with zlib for the IDAT chunk.
const compressed = zlib.deflateSync(raw);

/**
 * Computes the CRC-32 checksum of a Buffer using the standard PNG polynomial.
 * @param {Buffer} buf - The data to checksum.
 * @returns {number} The unsigned 32-bit CRC value.
 */
function crc32(buf) {
  let crc = 0xFFFFFFFF;
  const table = new Int32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++)
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    table[i] = c;
  }
  for (let i = 0; i < buf.length; i++)
    crc = table[(crc ^ buf[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

/**
 * Builds a single PNG chunk: [length][type][data][CRC32].
 * @param {string} type - Four-character chunk type (e.g. "IHDR").
 * @param {Buffer} data - Chunk payload.
 * @returns {Buffer} The full chunk including length and CRC.
 */
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const typeB = Buffer.from(type, "ascii");
  const crcData = Buffer.concat([typeB, data]);
  const crcB = Buffer.alloc(4);
  crcB.writeUInt32BE(crc32(crcData));
  return Buffer.concat([len, typeB, data, crcB]);
}

// 8-byte PNG file signature.
const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
// IHDR payload: width, height, bit depth (8), color type (6 = RGBA), no interlace.
const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(W, 0);
ihdr.writeUInt32BE(H, 4);
ihdr[8] = 8;
ihdr[9] = 6;
ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;

// Assemble the final PNG from signature and the three required chunks.
const png = Buffer.concat([
  sig, chunk("IHDR", ihdr), chunk("IDAT", compressed), chunk("IEND", Buffer.alloc(0)),
]);

// Write the generated tray icon to disk.
fs.writeFileSync(path.join(__dirname, "tray-icon.png"), png);
