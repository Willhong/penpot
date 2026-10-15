// E4 scenario: Plugin API code whose saved results depend on render-wasm
// computations (flex reflow, text size and position data, boolean paths).
// Runs unchanged as the body of an async function with `penpot` in scope,
// both in a browser workspace (wasm renderer) and in the headless executor.
// Every shape gets a stable name so the two saved files can be compared.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};

// 1. flex layout: wrapping row with fixed, fill and text children, then a
//    narrower container to force a re-wrap
const board = named(penpot.createBoard(), "flex-board");
board.x = 0;
board.y = 0;
board.resize(400, 300);
const flex = board.addFlexLayout();
flex.dir = "row";
flex.wrap = "wrap";
flex.rowGap = 10;
flex.columnGap = 10;
flex.topPadding = 20;
flex.rightPadding = 20;
flex.bottomPadding = 20;
flex.leftPadding = 20;
[[120, 60], [90, 80], [150, 40], [60, 60]].forEach(([w, h], i) => {
  const rect = named(penpot.createRectangle(), `flex-rect-${i}`);
  rect.resize(w, h);
  board.appendChild(rect);
});
const flexText = named(penpot.createText("Flex text child"), "flex-text");
flexText.fontSize = "24";
board.appendChild(flexText);
const fill = named(penpot.createRectangle(), "flex-fill");
fill.resize(50, 30);
board.appendChild(fill);
fill.layoutChild.horizontalSizing = "fill";
board.resize(260, 300);
flex.alignItems = "center";

// 2. text: auto-width single line with mixed scripts, and a wrapping
//    auto-height paragraph
const t1 = named(penpot.createText("Server MCP 텍스트 측정 Hello 123"), "text-auto-width");
t1.x = 0;
t1.y = 400;
t1.fontSize = "32";
t1.growType = "auto-width";
const t2 = named(penpot.createText("The quick brown fox jumps over the lazy dog again and again"), "text-auto-height");
t2.x = 0;
t2.y = 500;
t2.fontSize = "18";
t2.growType = "auto-height";
t2.resize(150, 20);

// 3. booleans over a rectangle and an ellipse
const bool = (type, x) => {
  const a = named(penpot.createRectangle(), `bool-${type}-rect`);
  a.x = x;
  a.y = 800;
  a.resize(100, 100);
  const b = named(penpot.createEllipse(), `bool-${type}-ellipse`);
  b.x = x + 50;
  b.y = 850;
  b.resize(100, 100);
  return named(penpot.createBoolean(type, [a, b]), `bool-${type}`);
};
bool("union", 0);
bool("difference", 200);
bool("intersection", 400);
bool("exclude", 600);

// Resizing an auto-height text leaves a `:text-bridge` mark that never
// drains in wasm mode, in the browser as well (E4 notes), so the wait is
// bounded; the computations themselves have finished by then.
await penpot.waitForLayoutUpdate(5000).catch(() => null);
return penpot.currentPage.findShapes().map((s) => s.name).sort();
