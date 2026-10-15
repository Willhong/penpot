// Compares two raster images pixel by pixel (03-runtime-contract §6: channel
// difference over 2 on at most 0.1% of the pixels). Runs inside the stack's
// main container, where the MCP server's `sharp` is installed:
//
//   node pixel_diff.mjs <a> <b>
//
// Prints {width, height, sameSize, pixels, differing, ratio, maxChannelDiff}.

import { createRequire } from "node:module";

const require = createRequire(`${process.env.HOME}/penpot/mcp/packages/server/package.json`);
const sharp = require("sharp");

const raw = async (path) => {
  const { data, info } = await sharp(path).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return { data, width: info.width, height: info.height };
};

const [a, b] = await Promise.all(process.argv.slice(2, 4).map(raw));
const out = { width: [a.width, b.width], height: [a.height, b.height], sameSize: a.width === b.width && a.height === b.height };
if (out.sameSize) {
  let differing = 0;
  let max = 0;
  for (let i = 0; i < a.data.length; i += 4) {
    let pixel = 0;
    for (let c = 0; c < 4; c++) pixel = Math.max(pixel, Math.abs(a.data[i + c] - b.data[i + c]));
    max = Math.max(max, pixel);
    if (pixel > 2) differing++;
  }
  out.pixels = a.data.length / 4;
  out.differing = differing;
  out.ratio = differing / out.pixels;
  out.maxChannelDiff = max;
}
console.log(JSON.stringify(out));
