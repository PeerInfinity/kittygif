// Draw a level from the emit-json pair the package produces -- the same
// `<prefix>_tilemap.json` + `<prefix>_tiles.json` the repository's samples ship,
// and the same colours, so the page and the committed preview PNGs agree.
//
// The colours are DERIVED in the package (each category takes the RGB of the gif
// id the table pairs it with) and two whole classes of id are deliberately left
// without one, because borrowing a substitute's colour would paint a conveyor or
// a spike in air's colour and delete it from the picture.  Here that shows up as
// `_color_from` being absent; those categories get an outline instead of a fill,
// so they stay visible as "something is here that the target format cannot say".

export function drawLevel(canvas, tilemap, config, opts = {}) {
  const w = tilemap.map_width, h = tilemap.map_height;
  const px = opts.scale || Math.max(2, Math.min(10, Math.floor(1000 / w)));
  canvas.width = w * px;
  canvas.height = h * px;
  canvas.style.maxWidth = Math.min(1000, w * px * 3) + "px";

  const ctx = canvas.getContext("2d");
  const cats = config.categories || {};
  const ids = config.tile_ids || {};
  const fallback = config.default_category;

  const empty = cats.empty && cats.empty.color ? cats.empty.color : "#000000";
  ctx.fillStyle = empty;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let y = 0; y < h; y++) {
    const row = tilemap.tiles[y];
    for (let x = 0; x < w; x++) {
      const cat = cats[ids[String(row[x])] || fallback];
      if (!cat) continue;
      if (cat.color) {
        if (cat.color === empty) continue;          // air, already painted
        ctx.fillStyle = cat.color;
        ctx.fillRect(x * px, y * px, px, px);
      } else {
        // no derived colour: outline it rather than invent one
        ctx.strokeStyle = "#8a8fae";
        ctx.lineWidth = Math.max(1, px / 5);
        ctx.strokeRect(x * px + px / 6, y * px + px / 6, px * 2 / 3, px * 2 / 3);
      }
    }
  }

  // A .kitty has no player-start CELL: the spawns are file fields, so they are
  // drawn from the metadata the emit-json pair carries rather than from the grid.
  for (const [key, colour] of [["robot_tile", "#ffffff"], ["kitty_tile", "#ff9f43"]]) {
    const at = tilemap[key];
    if (!at) continue;
    ctx.strokeStyle = colour;
    ctx.lineWidth = Math.max(1, px / 3);
    ctx.strokeRect(at[0] * px, at[1] * px, px, px);
  }
  return { scale: px, width: w, height: h };
}

export function legendFor(tilemap, config) {
  const used = new Set();
  for (const row of tilemap.tiles) for (const id of row) used.add(id);
  const ids = config.tile_ids || {};
  const seen = new Map();
  for (const id of used) {
    const name = ids[String(id)] || config.default_category;
    if (!seen.has(name)) seen.set(name, config.categories[name] || {});
  }
  return [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}
