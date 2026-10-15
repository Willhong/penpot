// PEN-5 scenario: creates rectangles, ellipses and boards, sets every basic
// property of the `shape` and `query` areas, clones and removes, and returns
// what the getters read back. Runs unchanged in a browser workspace and in
// the server-side executor (dual_run.py); every shape is named.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};

const gradient = (type) => ({
  type,
  startX: 0.1,
  startY: 0.2,
  endX: 0.9,
  endY: 0.8,
  width: 1,
  stops: [
    { color: "#ff0000", opacity: 1, offset: 0 },
    { color: "#0000ff", opacity: 0.5, offset: 1 },
  ],
});

// boards with view-mode and clipping options
const board = named(penpot.createBoard(), "board");
board.x = 0;
board.y = 0;
board.resize(600, 400);
board.clipContent = false;
board.showInViewMode = false;
board.fills = [{ fillColor: "#f1f3f5", fillOpacity: 1 }];

// a rectangle with every style property
const rect = named(penpot.createRectangle(), "rect");
board.appendChild(rect);
rect.x = 40;
rect.y = 50;
rect.resize(160, 90);
rect.borderRadius = 8;
rect.borderRadiusTopLeft = 2;
rect.borderRadiusBottomRight = 20;
rect.opacity = 0.75;
rect.blendMode = "multiply";
rect.proportionLock = true;
rect.fixedWhenScrolling = true;
rect.fills = [
  { fillColor: "#e8590c", fillOpacity: 0.9 },
  { fillColorGradient: gradient("linear"), fillOpacity: 1 },
];
rect.strokes = [
  { strokeColor: "#212529", strokeOpacity: 1, strokeStyle: "dashed", strokeWidth: 3, strokeAlignment: "inner" },
  { strokeColorGradient: gradient("radial"), strokeOpacity: 1, strokeStyle: "solid", strokeWidth: 1, strokeAlignment: "outer" },
];
rect.shadows = [
  { style: "drop-shadow", offsetX: 4, offsetY: 6, blur: 8, spread: 1, hidden: false, color: { color: "#000000", opacity: 0.3 } },
  { style: "inner-shadow", offsetX: -2, offsetY: 2, blur: 3, spread: 0, hidden: true, color: { color: "#1971c2", opacity: 0.6 } },
];
rect.blur = { value: 3, hidden: false };
rect.exports = [
  { type: "png", scale: 2, suffix: "@2x", skipChildren: false },
  { type: "svg", scale: 1, suffix: "", skipChildren: true },
];
rect.setPluginData("role", "card");
rect.setSharedPluginData("pen5", "tag", "styled");

// an ellipse, hidden and blocked, with a background blur
const ellipse = named(penpot.createEllipse(), "ellipse");
board.appendChild(ellipse);
ellipse.x = 260;
ellipse.y = 60;
ellipse.resize(120, 120);
ellipse.fills = [{ fillColorGradient: gradient("radial"), fillOpacity: 0.8 }];
ellipse.backgroundBlur = { value: 6, hidden: false };
ellipse.hidden = true;
ellipse.blocked = true;

// a top-level rectangle toggled through `visible`
const loose = named(penpot.createRectangle(), "loose");
loose.x = 700;
loose.y = 40;
loose.resize(80, 80);
loose.visible = false;
loose.visible = true;
loose.strokes = [{ strokeColor: "#2f9e44", strokeWidth: 4, strokeAlignment: "center", strokeStyle: "dotted" }];

// replacing a style array replaces it as a whole; editing a read copy changes nothing
const read = rect.fills;
read[0].fillColor = "#000000";

// clone, then remove the original of another clone
const copy = named(rect.clone(), "rect-copy");
copy.x = 40;
copy.y = 200;
const doomed = named(penpot.createEllipse(), "doomed");
const doomedCopy = named(doomed.clone(), "doomed-copy");
doomed.remove();

// read everything back
const page = penpot.currentPage;
const read2 = (s) => ({
  name: s.name,
  type: s.type,
  parent: s.parent ? s.parent.name : null,
  x: s.x,
  y: s.y,
  width: s.width,
  height: s.height,
  bounds: s.bounds,
  center: s.center,
  blocked: s.blocked,
  hidden: s.hidden,
  visible: s.visible,
  proportionLock: s.proportionLock,
  fixedWhenScrolling: s.fixedWhenScrolling,
  borderRadius: s.borderRadius,
  corners: [s.borderRadiusTopLeft, s.borderRadiusTopRight, s.borderRadiusBottomRight, s.borderRadiusBottomLeft],
  opacity: s.opacity,
  blendMode: s.blendMode,
  fills: s.fills,
  strokes: s.strokes,
  shadows: s.shadows.map((sh) => ({ ...sh, id: undefined })),
  blur: s.blur && { ...s.blur, id: undefined },
  backgroundBlur: s.backgroundBlur && { ...s.backgroundBlur, id: undefined },
  exports: s.exports,
  pluginData: [s.getPluginDataKeys(), s.getPluginData("role")],
  sharedPluginData: [s.getSharedPluginDataKeys("pen5"), s.getSharedPluginData("pen5", "tag")],
  clipContent: s.type === "board" ? s.clipContent : undefined,
  showInViewMode: s.type === "board" ? s.showInViewMode : undefined,
});
return {
  root: page.root.name,
  rootChildren: page.root.children.map((s) => s.name),
  byId: page.getShapeById(rect.id).name,
  byIdMissing: page.getShapeById("00000000-0000-4000-8000-000000000999"),
  found: page.findShapes({ type: "rectangle" }).map((s) => s.name).sort(),
  removed: page.findShapes({ name: "doomed" }).length,
  shapes: page.findShapes().filter((s) => s.name !== "Root Frame").map(read2).sort((a, b) => a.name.localeCompare(b.name)),
};
