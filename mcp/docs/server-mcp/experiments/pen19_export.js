// PEN-19 scenario: a fixed document mixing shapes, a gradient and a shadow,
// text in two scripts, a flex layout, a component copy and an image fill,
// then every export format and the code generation. Returns the outputs as
// base64 and strings. Runs unchanged in a browser workspace and in the
// server-side executor (pen19_exports.py compares them).

const IMAGE = "__PNG_BASE64__";

const named = (shape, name) => {
  shape.name = name;
  return shape;
};
const b64 = (bytes) => {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const [a, b, c] = [bytes[i], bytes[i + 1], bytes[i + 2]];
    const n = (a << 16) | ((b ?? 0) << 8) | (c ?? 0);
    out += alphabet[(n >> 18) & 63] + alphabet[(n >> 12) & 63];
    out += b === undefined ? "=" : alphabet[(n >> 6) & 63];
    out += c === undefined ? "=" : alphabet[n & 63];
  }
  return out;
};

const board = named(penpot.createBoard(), "card");
board.resize(360, 240);
board.fills = [{ fillColor: "#ffffff", fillOpacity: 1 }];
board.borderRadius = 12;
board.shadows = [{ style: "drop-shadow", offsetX: 0, offsetY: 4, blur: 12, spread: 0, hidden: false,
                   color: { color: "#000000", opacity: 0.2 } }];
const flex = board.addFlexLayout();
flex.dir = "column";
flex.rowGap = 12;
flex.horizontalPadding = 20;
flex.verticalPadding = 20;

const title = named(penpot.createText("Server export 서버 내보내기"), "title");
flex.appendChild(title);
title.fontSize = "22";
title.fontWeight = "700";
const row = named(penpot.createBoard(), "row");
flex.appendChild(row);
row.resize(320, 90);
const rowFlex = row.addFlexLayout();
rowFlex.columnGap = 10;
const swatch = named(penpot.createEllipse(), "swatch");
rowFlex.appendChild(swatch);
swatch.resize(80, 80);
swatch.fills = [{ fillOpacity: 1, fillColorGradient: { type: "linear", startX: 0, startY: 0, endX: 1, endY: 1, width: 1,
  stops: [{ color: "#e03131", opacity: 1, offset: 0 }, { color: "#1971c2", opacity: 1, offset: 1 }] } }];
const bytes = Uint8Array.from(atob(IMAGE), (c) => c.charCodeAt(0));
const image = await penpot.uploadMediaData("pixels", bytes, "image/png");
const photo = named(penpot.createRectangle(), "photo");
rowFlex.appendChild(photo);
photo.resize(120, 80);
photo.fills = [{ fillOpacity: 1, fillImage: image }];
const badge = named(penpot.createRectangle(), "badge");
badge.resize(60, 24);
badge.borderRadius = 12;
badge.fills = [{ fillColor: "#2f9e44", fillOpacity: 1 }];
const component = penpot.library.local.createComponent([badge]);
const copy = named(component.instance(), "badge-copy");
rowFlex.appendChild(copy);
const path = named(penpot.createPath(), "check");
flex.appendChild(path);
path.d = "M 0 10 L 8 18 L 24 0";
path.strokes = [{ strokeColor: "#2f9e44", strokeOpacity: 1, strokeStyle: "solid", strokeWidth: 3, strokeAlignment: "center" }];
await penpot.waitForLayoutUpdate(10000);

const outputs = {};
for (const [name, shape, options] of [
  ["card.png", board, { type: "png", scale: 1 }],
  ["card@2x.png", board, { type: "png", scale: 2 }],
  ["card.jpeg", board, { type: "jpeg", scale: 1 }],
  ["card.webp", board, { type: "webp", scale: 1 }],
  ["card.svg", board, { type: "svg", scale: 1 }],
  ["card.pdf", board, { type: "pdf", scale: 1 }],
  ["title.png", title, { type: "png", scale: 1 }],
  ["photo.png", photo, { type: "png", scale: 1 }],
]) {
  outputs[name] = b64(await shape.export(options));
}

return {
  outputs,
  code: {
    html: penpot.generateMarkup([board], { type: "html" }),
    svg: penpot.generateMarkup([board], { type: "svg" }),
    css: penpot.generateStyle([board], { type: "css", withChildren: true }),
    cssPrepend: penpot.generateStyle([board], { type: "css", withPrelude: true, includeChildren: false }),
    fonts: await penpot.generateFontFaces([board]),
  },
  ids: Object.fromEntries([board, title, row, swatch, photo, copy, path].map((s) => [s.id, s.name])),
};
