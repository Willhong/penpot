// PEN-9 gap scenario (1/3): Plugin API members no earlier scenario ran on the
// server. Execution context, flags, group and boolean
// children, path data and its commands,
// fonts and text ranges, grid tracks and child margins, guides, flows and
// interactions. Every call goes through `tryv`, so a refusal is compared like
// a value. Runs unchanged in a browser workspace and in the server-side
// executor (pen9_gaps.py); every shape is named.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};
const tryv = (f) => {
  try {
    const v = f();
    return v === undefined ? null : v;
  } catch (error) {
    return "ERR " + String(error.message || error);
  }
};
const settle = async () => {
  try {
    await penpot.waitForLayoutUpdate(10000);
    return "ok";
  } catch (error) {
    return String(error.message || error);
  }
};
const r2 = (n) => (typeof n === "number" ? Math.round(n * 100) / 100 : n);
const out = {};

// --- execution context
out.root = tryv(() => penpot.root && penpot.root.name);
const rect = named(penpot.createRectangle(), "rect");
const ell = named(penpot.createEllipse(), "ell");
ell.x = 200;
const board = named(penpot.createBoard(), "board");
board.x = 400;
board.resize(300, 300);
const a = named(penpot.createRectangle(), "a");
const b = named(penpot.createRectangle(), "b");
b.x = 60;
const group = named(penpot.group([a, b]), "group");
const m1 = named(penpot.createRectangle(), "m1");
const m2 = named(penpot.createEllipse(), "m2");
const mask = named(penpot.group([m1, m2]), "mask");
mask.makeMask();
const p1 = named(penpot.createRectangle(), "p1");
const p2 = named(penpot.createRectangle(), "p2");
p2.x = 20;
const bool = named(penpot.createBoolean("union", [p1, p2]), "bool");
const path = named(penpot.createPath(), "path");
path.d = "M 0 0 L 40 0 L 40 40 Z";
const text = named(penpot.createText("Range text 범위"), "text");
const svg = penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8" fill="#f03e3e"/></svg>');
if (svg) svg.name = "svg";
out.settle1 = await settle();
// (penpot.utils comes from the plugins runtime, which the browser side of the comparison does not load:
// pen9_gaps.py checks it on the server against the shapes' own answers)

// --- flags
out.flags = [penpot.flags.naturalChildOrdering, penpot.flags.throwValidationErrors];
penpot.flags.throwValidationErrors = false;
out.noThrow = tryv(() => {
  rect.opacity = 7;
  return "accepted";
});
penpot.flags.throwValidationErrors = true;
out.withThrow = tryv(() => {
  rect.opacity = 7;
  return "accepted";
});
const c1 = named(penpot.createRectangle(), "c1");
const c2 = named(penpot.createRectangle(), "c2");
board.appendChild(c1);
board.appendChild(c2);
penpot.flags.naturalChildOrdering = false;
out.childrenReversed = board.children.map((c) => c.name);
penpot.flags.naturalChildOrdering = true;
out.childrenNatural = board.children.map((c) => c.name);

// (`penpot.version` and `penpot.localStorage` depend on the build and the plugins runtime's permission
// check, which the browser side of the comparison skips: pen9_gaps.py checks them on the server)

// (event subscriptions come from the plugins runtime too: pen9_gaps.py checks them on the server)

// --- group and boolean children, place in parent, position in board
const g3 = named(penpot.createRectangle(), "g3");
group.appendChild(g3);
const g0 = named(penpot.createRectangle(), "g0");
group.insertChild(0, g0);
out.groupChildren = group.children.map((c) => [c.name, c.parentIndex]);
const p3 = named(penpot.createRectangle(), "p3");
p3.x = 30;
bool.appendChild(p3);
const p0 = named(penpot.createRectangle(), "p0");
bool.insertChild(0, p0);
out.boolChildren = bool.children.map((c) => c.name);
c1.boardX = 15;
c1.boardY = 25;
out.boardXY = [c1.boardX, c1.boardY, r2(c1.x), r2(c1.y)];

// --- path data and commands
path.content = "M 0 0 L 10 10 L 20 0";
out.pathContent = path.content;
path.d = "M 0 0 A 10 12 30 0 1 20 20 C 25 25 30 30 40 40 Q 45 45 50 50 Z";
out.commands = path.commands.map((c) => [c.command, c.params
  ? ["x", "y", "c1x", "c1y", "c2x", "c2y", "rx", "ry", "xAxisRotation", "largeArcFlag", "sweepFlag"]
    .map((k) => [k, r2(c.params[k]) ?? null])
  : null]);
out.settle2 = await settle();
out.bool = [bool.content.length > 0, bool.d.length > 0, bool.commands.length > 0, bool.content === bool.d];

// --- fonts and text ranges
const font = penpot.fonts.findById("sourcesanspro");
out.font = font && [font.name, font.fontId, font.fontFamily, font.fontStyle, font.fontVariantId, font.fontWeight,
  font.variants.slice(0, 3).map((v) => [v.name, v.fontVariantId])];
out.fontsById = penpot.fonts.findAllById("sourcesanspro").map((f) => f.fontId);
out.fontsByName = penpot.fonts.findAllByName("Roboto").map((f) => f.fontId).slice(0, 3);
out.settle3 = await settle();
out.textType = text.type;
out.textBounds = tryv(() => {
  const tb = text.textBounds;
  return [r2(tb.x), r2(tb.y), r2(tb.width), r2(tb.height)];
});
const range = text.getRange(0, 5);
range.lineHeight = "1.5";
range.textTransform = "uppercase";
range.direction = "rtl";
range.align = "center";
range.verticalAlign = "bottom";
out.range = [range.shape.name, range.fontId, range.fontVariantId, range.lineHeight, range.textTransform,
  range.direction, range.align, range.verticalAlign];
const typo = penpot.library.local.createTypography();
typo.name = "Gap";
typo.fontSize = "18";
const text2 = named(penpot.createText("Typography target"), "text2");
text2.y = 300;
out.settle4 = await settle();
text2.applyTypography(typo);
text.getRange(6, 10).applyTypography(typo);
out.settle5 = await settle();
out.typographyApplied = [text2.fontSize, text.getRange(6, 10).fontSize];

// --- grid tracks, cell area, child margins
const gb = named(penpot.createBoard(), "gridboard");
gb.y = 500;
gb.resize(300, 200);
const gl = gb.addGridLayout();
out.boardGrid = !!gb.grid;
gl.dir = "row";
gl.addRow("flex", 1);
gl.addColumn("flex", 1);
gl.addRowAtIndex(0, "fixed", 50);
gl.addColumnAtIndex(0, "fixed", 60);
gl.setColumn(0, "percent", 30);
const cellChild = named(penpot.createRectangle(), "cell");
gl.appendChild(cellChild, 1, 1);
out.settle6 = await settle();
out.grid = [gl.dir, gl.rows.map((r) => [r.type, r.value]), gl.columns.map((c) => [c.type, c.value])];
out.cellArea = tryv(() => {
  cellChild.layoutCell.areaName = "hero";
  return cellChild.layoutCell.areaName;
});
const fb = named(penpot.createBoard(), "flexboard");
fb.y = 800;
const fl = fb.addFlexLayout();
fl.dir = "column";
const fc = named(penpot.createRectangle(), "flexchild");
fl.appendChild(fc);
const lc = fc.layoutChild;
lc.horizontalMargin = 4;
lc.verticalMargin = 6;
lc.rightMargin = 8;
lc.bottomMargin = 2;
lc.minHeight = 10;
out.margins = [lc.horizontalMargin, lc.verticalMargin, lc.rightMargin, lc.bottomMargin, lc.minHeight];
out.shapeWait = await (async () => {
  try {
    await fc.waitForLayoutUpdate(10000);
    return "ok";
  } catch (error) {
    return String(error.message || error);
  }
})();
out.childBox = [r2(fc.x), r2(fc.y), r2(fc.width), r2(fc.height)];

// --- guides, flows, interactions
const columns = { type: "column", display: true,
  params: { color: { color: "#ff0000", opacity: 0.1 }, type: "stretch", size: 4, margin: 0, itemLength: 20, gutter: 8 } };
board.guides = [columns];
out.guideItemLength = tryv(() => board.guides[0].params.itemLength);
const boardGuide = board.addRulerGuide("vertical", 10);
out.boardRulerGuides = board.rulerGuides.length;
board.removeRulerGuide(boardGuide);
out.boardRulerGuidesAfter = board.rulerGuides.length;
const pageGuide = penpot.currentPage.addRulerGuide("horizontal", 30);
penpot.currentPage.removeRulerGuide(pageGuide);
out.pageRulerGuides = penpot.currentPage.rulerGuides.length;
const target = named(penpot.createBoard(), "target");
target.x = 800;
const overlay = named(penpot.createBoard(), "overlay");
overlay.x = 1200;
const flow = penpot.currentPage.createFlow("Gap flow", board);
out.flowPage = flow.page.name;
flow.remove();
out.flowsAfter = penpot.currentPage.flows.length;
const nav = rect.addInteraction("click", { type: "navigate-to", destination: target });
out.interactionShape = nav.shape && nav.shape.name;
// an overlay needs its shape inside a board: elsewhere both sides drop it without a word
const over = c1.addInteraction("click", { type: "open-overlay", destination: overlay, relativeTo: target,
  position: "manual", manualPositionLocation: { x: 10, y: 20 } });
out.overlay = tryv(() => [over.action.relativeTo && over.action.relativeTo.name,
  over.action.manualPositionLocation && [over.action.manualPositionLocation.x, over.action.manualPositionLocation.y]]);
rect.removeInteraction(nav);
out.interactionsAfter = rect.interactions.length;

return out;
