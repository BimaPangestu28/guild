/**
 * Renders the Interior_1st_floor.tmx tilemap to a PNG image.
 * Outputs to dashboard/public/assets/guild-hall-interior.png
 */
import { createCanvas, loadImage } from 'canvas';
import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';

const ASSET_DIR = '/mnt/c/Users/bimap/Downloads/craftpix-net-189780-free-top-down-pixel-art-guild-hall-asset-pack';
const TILED_DIR = `${ASSET_DIR}/Tiled_files`;
const TMX_PATH = `${TILED_DIR}/Interior_1st_floor.tmx`;
const TILE_SIZE = 16;
const SCALE = 3;

// Simple XML parser for TMX (no external dep needed)
function parseTMX(xmlStr) {
  const tilesets = [];
  const layers = [];

  // Parse tilesets
  const tsRegex = /<tileset firstgid="(\d+)" name="([^"]*)" tilewidth="\d+" tileheight="\d+" tilecount="\d+" columns="(\d+)">\s*<image source="([^"]*)" width="(\d+)" height="(\d+)"\/>/g;
  let m;
  while ((m = tsRegex.exec(xmlStr)) !== null) {
    tilesets.push({
      firstgid: parseInt(m[1]),
      name: m[2],
      columns: parseInt(m[3]),
      source: m[4],
      width: parseInt(m[5]),
      height: parseInt(m[6]),
    });
  }

  // Parse layers with chunks
  const layerRegex = /<layer id="\d+" name="([^"]*)"[^>]*>([\s\S]*?)<\/layer>/g;
  while ((m = layerRegex.exec(xmlStr)) !== null) {
    const name = m[1];
    const layerContent = m[2];
    const chunks = [];

    const chunkRegex = /<chunk x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)">\s*([\s\S]*?)\s*<\/chunk>/g;
    let cm;
    while ((cm = chunkRegex.exec(layerContent)) !== null) {
      const tiles = cm[5].split(',').map(t => parseInt(t.trim())).filter(t => !isNaN(t));
      chunks.push({
        x: parseInt(cm[1]),
        y: parseInt(cm[2]),
        width: parseInt(cm[3]),
        height: parseInt(cm[4]),
        tiles,
      });
    }
    layers.push({ name, chunks });
  }

  return { tilesets, layers };
}

async function main() {
  const xml = readFileSync(TMX_PATH, 'utf-8');
  const { tilesets, layers } = parseTMX(xml);

  console.log(`Parsed ${tilesets.length} tilesets, ${layers.length} layers`);

  // Determine map bounds from chunks
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
  console.log(`Map bounds: ${minX},${minY} to ${maxX},${maxY} = ${mapWidth}x${mapHeight} tiles`);

  const canvas = createCanvas(mapWidth * TILE_SIZE, mapHeight * TILE_SIZE);
  const ctx = canvas.getContext('2d');

  // Load tileset images
  const images = {};
  for (const ts of tilesets) {
    const imgPath = resolve(TILED_DIR, ts.source);
    try {
      images[ts.name] = await loadImage(imgPath);
      console.log(`Loaded: ${ts.name} (${ts.source})`);
    } catch (e) {
      console.warn(`MISSING: ${ts.name} (${ts.source}) — will skip tiles from this tileset`);
      images[ts.name] = null;
    }
  }

  // Sort tilesets by firstgid descending for lookup
  const sortedTs = [...tilesets].sort((a, b) => b.firstgid - a.firstgid);

  function findTileset(gid) {
    for (const ts of sortedTs) {
      if (gid >= ts.firstgid) return ts;
    }
    return null;
  }

  // Render layers in order (skip character/animation layers for static render)
  const skipLayers = new Set(['Guildmaster', 'Various_characters']);

  for (const layer of layers) {
    if (skipLayers.has(layer.name)) continue;

    for (const chunk of layer.chunks) {
      for (let i = 0; i < chunk.tiles.length; i++) {
        const gid = chunk.tiles[i];
        if (gid === 0) continue;

        const ts = findTileset(gid);
        if (!ts || !images[ts.name]) continue;

        const localId = gid - ts.firstgid;
        const srcCol = localId % ts.columns;
        const srcRow = Math.floor(localId / ts.columns);

        const tileX = i % chunk.width;
        const tileY = Math.floor(i / chunk.width);
        const destX = (chunk.x - minX + tileX) * TILE_SIZE;
        const destY = (chunk.y - minY + tileY) * TILE_SIZE;

        ctx.drawImage(
          images[ts.name],
          srcCol * TILE_SIZE, srcRow * TILE_SIZE, TILE_SIZE, TILE_SIZE,
          destX, destY, TILE_SIZE, TILE_SIZE
        );
      }
    }
  }

  // Now render Guildmaster (first frame only - static)
  for (const layer of layers) {
    if (layer.name !== 'Guildmaster' && layer.name !== 'Various_characters') continue;
    for (const chunk of layer.chunks) {
      for (let i = 0; i < chunk.tiles.length; i++) {
        const gid = chunk.tiles[i];
        if (gid === 0) continue;

        const ts = findTileset(gid);
        if (!ts || !images[ts.name]) continue;

        const localId = gid - ts.firstgid;
        const srcCol = localId % ts.columns;
        const srcRow = Math.floor(localId / ts.columns);

        const tileX = i % chunk.width;
        const tileY = Math.floor(i / chunk.width);
        const destX = (chunk.x - minX + tileX) * TILE_SIZE;
        const destY = (chunk.y - minY + tileY) * TILE_SIZE;

        ctx.drawImage(
          images[ts.name],
          srcCol * TILE_SIZE, srcRow * TILE_SIZE, TILE_SIZE, TILE_SIZE,
          destX, destY, TILE_SIZE, TILE_SIZE
        );
      }
    }
  }

  // Scale up for pixel-perfect look
  const scaledCanvas = createCanvas(mapWidth * TILE_SIZE * SCALE, mapHeight * TILE_SIZE * SCALE);
  const sctx = scaledCanvas.getContext('2d');
  sctx.imageSmoothingEnabled = false;
  sctx.drawImage(canvas, 0, 0, scaledCanvas.width, scaledCanvas.height);

  // Save
  const outPath = resolve('dashboard/public/assets/guild-hall-interior.png');
  writeFileSync(outPath, scaledCanvas.toBuffer('image/png'));
  console.log(`\nSaved: ${outPath} (${scaledCanvas.width}x${scaledCanvas.height})`);

  // Also save 1x version
  const outPath1x = resolve('dashboard/public/assets/guild-hall-interior-1x.png');
  writeFileSync(outPath1x, canvas.toBuffer('image/png'));
  console.log(`Saved: ${outPath1x} (${canvas.width}x${canvas.height})`);
}

main().catch(console.error);
