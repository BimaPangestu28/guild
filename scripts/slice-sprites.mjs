/**
 * Slice sprite sheets into individual idle animation strips.
 * Uses correct frame sizes per sprite type.
 */
import { createCanvas, loadImage } from 'canvas';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve } from 'path';

const ASSET_DIR = '/mnt/c/Users/bimap/Downloads/craftpix-net-189780-free-top-down-pixel-art-guild-hall-asset-pack/PNG';
const OUT_DIR = resolve('dashboard/public/assets/sprites/sliced');
const SCALE = 3;

mkdirSync(OUT_DIR, { recursive: true });

/**
 * Each sprite definition:
 *   file: source PNG
 *   name: output name
 *   fw/fh: frame width/height in pixels (unscaled)
 *   cols: number of frames in the idle row
 *   row: which row is the front-facing idle (0-indexed)
 */
const sprites = [
  // Citizen-type: 32x32 grid, row 0 = facing front, 12 frames
  { file: 'Citizen1_Idle_without_shadow.png', name: 'citizen1', fw: 32, fh: 32, cols: 12, row: 0 },
  { file: 'Citizen2_Idle_without_shadow.png', name: 'citizen2', fw: 32, fh: 32, cols: 12, row: 0 },
  { file: 'Fighter2_Idle_without_shadow.png', name: 'fighter2', fw: 32, fh: 32, cols: 12, row: 0 },

  // Mage-type: 64x52 grid, row 0 = front, first 3 frames are pure idle
  { file: 'Mage1_without_shadow.png', name: 'mage1', fw: 64, fh: 52, cols: 3, row: 0 },
  { file: 'Mage2_without_shadow.png', name: 'mage2', fw: 64, fh: 52, cols: 3, row: 0 },
  { file: 'Mage3_without_shadow.png', name: 'mage3', fw: 64, fh: 52, cols: 3, row: 0 },
  { file: 'Mage4_without_shadow.png', name: 'mage4', fw: 64, fh: 52, cols: 3, row: 0 },

  // Fighter with sword: 64x64 grid, row 0 = front, first 3 frames are idle stance
  { file: 'Fighter_sword_without_shadow.png', name: 'fighter-sword', fw: 64, fh: 64, cols: 3, row: 0 },

  // Guildmaster: 48x32, 6 frames, single row
  { file: 'Guildmaster.png', name: 'guildmaster', fw: 48, fh: 32, cols: 6, row: 0 },

  // Reader1: 32x48, 11 frames, single row
  { file: 'Reader1.png', name: 'reader1', fw: 32, fh: 48, cols: 11, row: 0 },

  // Fire: 48x48, frames 2-4 are the looping flame
  { file: 'Fire.png', name: 'fire', fw: 48, fh: 48, cols: 3, row: 0, startFrame: 2 },
];

async function main() {
  const meta = [];

  for (const spec of sprites) {
    const img = await loadImage(resolve(ASSET_DIR, spec.file));
    const { fw, fh, cols, row, name } = spec;

    // Create scaled strip
    const stripW = cols * fw * SCALE;
    const stripH = fh * SCALE;
    const canvas = createCanvas(stripW, stripH);
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;

    const startFrame = spec.startFrame || 0;
    for (let f = 0; f < cols; f++) {
      const sx = (f + startFrame) * fw;
      const sy = row * fh;

      ctx.drawImage(
        img,
        sx, sy, fw, fh,
        f * fw * SCALE, 0, fw * SCALE, fh * SCALE
      );
    }

    const outFile = `${name}-idle.png`;
    writeFileSync(`${OUT_DIR}/${outFile}`, canvas.toBuffer('image/png'));
    meta.push({
      name,
      file: outFile,
      frames: cols,
      frameWidth: fw * SCALE,
      frameHeight: fh * SCALE,
      originalFrameSize: `${fw}x${fh}`,
    });
    console.log(`${name}: ${cols} frames @ ${fw}x${fh} -> ${outFile} (${stripW}x${stripH})`);
  }

  writeFileSync(`${OUT_DIR}/sprites.json`, JSON.stringify(meta, null, 2));
  console.log(`\nDone! ${meta.length} sprite strips.`);
}

main().catch(console.error);
