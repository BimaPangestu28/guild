import { createCanvas, loadImage } from 'canvas';
import { readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';

const ASSET_DIR = '/mnt/c/Users/bimap/Downloads/craftpix-net-189780-free-top-down-pixel-art-guild-hall-asset-pack';
const TILED_DIR = `${ASSET_DIR}/Tiled_files`;
const TMX_PATH = `${TILED_DIR}/Exterior.tmx`;
const TILE_SIZE = 16;
const SCALE = 3;

function parseTMX(xmlStr) {
  const tilesets = [];
  const layers = [];
  const tsRegex = /<tileset firstgid="(\d+)" name="([^"]*)" tilewidth="\d+" tileheight="\d+" tilecount="\d+" columns="(\d+)">\s*<image source="([^"]*)" width="(\d+)" height="(\d+)"\/>/g;
  let m;
  while ((m = tsRegex.exec(xmlStr)) !== null) {
    tilesets.push({ firstgid: parseInt(m[1]), name: m[2], columns: parseInt(m[3]), source: m[4] });
  }
  const layerRegex = /<layer id="\d+" name="([^"]*)"[^>]*>([\s\S]*?)<\/layer>/g;
  while ((m = layerRegex.exec(xmlStr)) !== null) {
    const chunks = [];
    const chunkRegex = /<chunk x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)">\s*([\s\S]*?)\s*<\/chunk>/g;
    let cm;
    while ((cm = chunkRegex.exec(m[2])) !== null) {
      chunks.push({
        x: parseInt(cm[1]), y: parseInt(cm[2]),
        width: parseInt(cm[3]), height: parseInt(cm[4]),
        tiles: cm[5].split(',').map(t => parseInt(t.trim())).filter(t => !isNaN(t)),
      });
    }
    layers.push({ name: m[1], chunks });
  }
  return { tilesets, layers };
}

async function main() {
  const xml = readFileSync(TMX_PATH, 'utf-8');
  const { tilesets, layers } = parseTMX(xml);
  console.log(`Parsed ${tilesets.length} tilesets, ${layers.length} layers`);

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const layer of layers) {
    for (const chunk of layer.chunks) {
      minX = Math.min(minX, chunk.x);
      minY = Math.min(minY, chunk.y);
      maxX = Math.max(maxX, chunk.x + chunk.width);
      maxY = Math.max(maxY, chunk.y + chunk.height);
    }
  }
  const mapWidth = maxX - minX;
  const mapHeight = maxY - minY;
  console.log(`Map: ${mapWidth}x${mapHeight} tiles`);

  const canvas = createCanvas(mapWidth * TILE_SIZE, mapHeight * TILE_SIZE);
  const ctx = canvas.getContext('2d');

  const images = {};
  const sortedTs = [...tilesets].sort((a, b) => b.firstgid - a.firstgid);
  for (const ts of tilesets) {
    try {
      images[ts.name] = await loadImage(resolve(TILED_DIR, ts.source));
      console.log(`Loaded: ${ts.name}`);
    } catch { images[ts.name] = null; console.warn(`MISSING: ${ts.name}`); }
  }

  for (const layer of layers) {
    for (const chunk of layer.chunks) {
      for (let i = 0; i < chunk.tiles.length; i++) {
        const gid = chunk.tiles[i];
        if (gid === 0) continue;
        const ts = sortedTs.find(t => gid >= t.firstgid);
        if (!ts || !images[ts.name]) continue;
        const localId = gid - ts.firstgid;
        const srcCol = localId % ts.columns;
        const srcRow = Math.floor(localId / ts.columns);
        const tileX = i % chunk.width;
        const tileY = Math.floor(i / chunk.width);
        ctx.drawImage(images[ts.name],
          srcCol * TILE_SIZE, srcRow * TILE_SIZE, TILE_SIZE, TILE_SIZE,
          (chunk.x - minX + tileX) * TILE_SIZE, (chunk.y - minY + tileY) * TILE_SIZE, TILE_SIZE, TILE_SIZE
        );
      }
    }
  }

  const sc = createCanvas(mapWidth * TILE_SIZE * SCALE, mapHeight * TILE_SIZE * SCALE);
  const sctx = sc.getContext('2d');
  sctx.imageSmoothingEnabled = false;
  sctx.drawImage(canvas, 0, 0, sc.width, sc.height);

  writeFileSync(resolve('dashboard/public/assets/guild-hall-exterior.png'), sc.toBuffer('image/png'));
  console.log(`Saved exterior (${sc.width}x${sc.height})`);
}

main().catch(console.error);
