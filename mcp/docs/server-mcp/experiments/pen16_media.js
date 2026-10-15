// PEN-16 scenario: images and SVG. Uploads an image from bytes and one from a
// public URL, fills shapes with them, imports an SVG with paths, gradients,
// groups and transforms, and one with an embedded and an external image.
// Returns what the getters read back. Runs unchanged in a browser workspace and
// in the server-side executor (dual_run.py); every shape is named.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};
// an 8x6 PNG
const png = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAGCAIAAABxZ0isAAAAEUlEQVR4nGOQLDyEFTEMpAQAHrQ+QRItThwAAAAASUVORK5CYII="), (c) => c.charCodeAt(0));
const fromBytes = await penpot.uploadMediaData("bytes", png, "image/png");
const fromUrl = await penpot.uploadMediaUrl("w3c", "https://www.w3.org/Icons/w3c_home.png");
const a = named(penpot.createRectangle(), "filled-bytes");
a.resize(80, 60);
a.fills = [{ fillOpacity: 1, fillImage: fromBytes }];
const b = named(penpot.createEllipse(), "filled-url");
b.x = 100;
b.resize(72, 48);
b.fills = [{ fillOpacity: 0.8, fillImage: fromUrl }];

const svg = named(penpot.createShapeFromSvg(`<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120" viewBox="0 0 200 120">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e03131"/><stop offset="1" stop-color="#1971c2"/></linearGradient></defs>
  <g transform="translate(10 10)">
    <rect width="80" height="50" rx="8" fill="url(#g)"/>
    <path d="M100 0 L160 0 L130 50 Z" fill="#2f9e44" stroke="#000" stroke-width="2"/>
    <circle cx="40" cy="80" r="20" fill="none" stroke="#f08c00" stroke-width="4"/>
    <g transform="rotate(15 150 80)"><ellipse cx="150" cy="80" rx="30" ry="12" fill="#5f3dc4" opacity="0.6"/></g>
  </g>
</svg>`), "imported-svg");
svg.x = 0;
svg.y = 120;
const withImages = named(await penpot.createShapeFromSvgWithImages(`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="120" height="40">
  <image x="0" y="0" width="40" height="30" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAGCAIAAABxZ0isAAAAEUlEQVR4nGOQLDyEFTEMpAQAHrQ+QRItThwAAAAASUVORK5CYII="/>
  <image x="50" y="0" width="60" height="40" xlink:href="https://www.w3.org/Icons/w3c_home.png"/>
</svg>`), "svg-with-images");
withImages.x = 250;
await penpot.waitForLayoutUpdate(10000);

const image = (img) => img && { name: img.name, width: img.width, height: img.height, mtype: img.mtype, keepAspectRatio: img.keepAspectRatio };
const tree = (shape) => ({
  name: shape.name, type: shape.type, x: shape.x, y: shape.y, w: shape.width, h: shape.height, rotation: shape.rotation,
  fills: shape.fills === "mixed" ? "mixed" : shape.fills.map((f) => ({ color: f.fillColor, opacity: f.fillOpacity,
    gradient: f.fillColorGradient ? f.fillColorGradient.type : null, image: image(f.fillImage) })),
  strokes: shape.strokes.map((s) => [s.strokeColor, s.strokeWidth]),
  children: shape.children ? shape.children.map(tree) : undefined,
});
return {
  uploads: [image(fromBytes), image(fromUrl)],
  shapes: [a, b, svg, withImages].map(tree),
};
