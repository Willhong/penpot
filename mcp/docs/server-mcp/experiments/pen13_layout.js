// PEN-13 scenario: flex and grid layouts, nested, with every container and
// child option, then the changes that reflow them: parent resize, children
// added, removed, hidden, reordered, and a layout removed. After each step it
// waits for the layout and records the geometry of every shape. Runs
// unchanged in a browser workspace and in the server-side executor
// (dual_run.py); every shape is named.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};

const box = (name, width, height, color) => {
  const shape = named(penpot.createRectangle(), name);
  shape.resize(width, height);
  shape.fills = [{ fillColor: color, fillOpacity: 1 }];
  return shape;
};

const frame = (name, x, y, width, height) => {
  const shape = named(penpot.createBoard(), name);
  shape.x = x;
  shape.y = y;
  shape.resize(width, height);
  shape.fills = [{ fillColor: "#f1f3f5", fillOpacity: 1 }];
  return shape;
};

const waits = [];
const settle = async (label) => {
  try {
    await penpot.waitForLayoutUpdate(10000);
    waits.push([label, "ok"]);
  } catch (error) {
    waits.push([label, String(error.message || error)]);
  }
};

const all = [];
const geometry = () =>
  Object.fromEntries(
    all.map((shape) => [
      shape.name,
      [shape.x, shape.y, shape.width, shape.height, shape.hidden, shape.parent ? shape.parent.name : null].map((v) =>
        typeof v === "number" ? Math.round(v * 100) / 100 : v
      ),
    ])
  );
const steps = {};
const record = async (label) => {
  await settle(label);
  steps[label] = geometry();
};

// --- flex row: padding, gaps, alignment, wrap, child sizing, margins, limits
const row = frame("row", 0, 0, 520, 200);
const flex = row.addFlexLayout();
flex.dir = "row";
flex.wrap = "wrap";
flex.alignItems = "center";
flex.justifyContent = "space-between";
flex.alignContent = "space-around";
flex.rowGap = 12;
flex.columnGap = 16;
flex.paddingType = "multiple";
flex.topPadding = 10;
flex.rightPadding = 20;
flex.bottomPadding = 30;
flex.leftPadding = 40;
const r1 = box("r1", 80, 60, "#e03131");
const r2 = box("r2", 120, 40, "#1971c2");
const r3 = box("r3", 60, 90, "#2f9e44");
const r4 = box("r4", 100, 50, "#f08c00");
const r5 = box("r5", 50, 50, "#5f3dc4");
for (const child of [r1, r2, r3, r4, r5]) {
  flex.appendChild(child);
}
r2.layoutChild.horizontalSizing = "fill";
r2.layoutChild.maxWidth = 200;
r2.layoutChild.minWidth = 90;
r3.layoutChild.alignSelf = "end";
r3.layoutChild.marginType = "multiple";
r3.layoutChild.topMargin = 4;
r3.layoutChild.leftMargin = 8;
r4.layoutChild.verticalSizing = "fill";
r4.layoutChild.maxHeight = 70;
r5.layoutChild.absolute = true;
r5.layoutChild.zIndex = 3;
r5.x = 460;
r5.y = 150;
all.push(row, r1, r2, r3, r4, r5);
await record("flexRow");

// --- nested: a hugging column inside a hugging row inside a fixed board
const outer = frame("outer", 0, 260, 600, 300);
const outerFlex = outer.addFlexLayout();
outerFlex.dir = "column";
outerFlex.alignItems = "stretch";
outerFlex.rowGap = 8;
outerFlex.horizontalPadding = 12;
outerFlex.verticalPadding = 12;
const middle = frame("middle", 0, 0, 100, 100);
outerFlex.appendChild(middle);
const middleFlex = middle.addFlexLayout();
middleFlex.dir = "row";
middleFlex.columnGap = 6;
middleFlex.horizontalSizing = "auto";
middleFlex.verticalSizing = "auto";
middleFlex.horizontalPadding = 4;
middleFlex.verticalPadding = 4;
const inner = frame("inner", 0, 0, 50, 50);
middleFlex.appendChild(inner);
const innerFlex = inner.addFlexLayout();
innerFlex.dir = "column-reverse";
innerFlex.rowGap = 4;
innerFlex.horizontalSizing = "auto";
innerFlex.verticalSizing = "auto";
innerFlex.justifyContent = "end";
const i1 = box("i1", 40, 20, "#0c8599");
const i2 = box("i2", 70, 30, "#66a80f");
innerFlex.appendChild(i1);
innerFlex.appendChild(i2);
const m2 = box("m2", 90, 45, "#d6336c");
middleFlex.appendChild(m2);
const tail = box("tail", 50, 40, "#868e96");
outerFlex.appendChild(tail);
tail.layoutChild.horizontalSizing = "fill";
all.push(outer, middle, inner, i1, i2, m2, tail);
await record("nested");

// --- grid: every track type, spans, a grid nested in a flex child
const grid = frame("grid", 640, 0, 420, 320);
const gl = grid.addGridLayout();
gl.addColumn("fixed", 100);
gl.addColumn("flex", 1);
gl.addColumn("percent", 25);
gl.addRow("auto");
gl.addRow("flex", 2);
gl.addRow("fixed", 60);
gl.rowGap = 10;
gl.columnGap = 8;
gl.horizontalPadding = 10;
gl.verticalPadding = 10;
gl.justifyItems = "center";
const g1 = box("g1", 50, 30, "#e03131");
const g2 = box("g2", 70, 40, "#1971c2");
const g3 = box("g3", 30, 30, "#2f9e44");
const g4 = box("g4", 60, 20, "#f08c00");
gl.appendChild(g1, 1, 1);
gl.appendChild(g2, 1, 2);
gl.appendChild(g3, 2, 1);
gl.appendChild(g4, 3, 2);
g2.layoutCell.columnSpan = 2;
g3.layoutCell.rowSpan = 2;
g4.layoutChild.horizontalSizing = "fill";
g1.layoutChild.alignSelf = "end";
const nestedGrid = frame("nestedGrid", 0, 0, 120, 80);
outerFlex.appendChild(nestedGrid);
const ngl = nestedGrid.addGridLayout();
ngl.addColumn("flex", 1);
ngl.addColumn("flex", 1);
ngl.addRow("flex", 1);
const n1 = box("n1", 20, 20, "#5f3dc4");
ngl.appendChild(n1, 1, 2);
n1.layoutChild.horizontalSizing = "fill";
n1.layoutChild.verticalSizing = "fill";
all.push(grid, g1, g2, g3, g4, nestedGrid, n1);
await record("grid");

// --- reflows
row.resize(360, 200);
grid.resize(500, 360);
await record("parentsResized");

const added = box("added", 70, 70, "#495057");
middleFlex.appendChild(added);
all.push(added);
const gAdded = box("gAdded", 40, 40, "#495057");
gl.appendChild(gAdded, 3, 3);
all.push(gAdded);
await record("childrenAdded");

i2.hidden = true;
r1.hidden = true;
await record("childrenHidden");

m2.setParentIndex(0);
outer.insertChild(0, tail);
await record("reordered");

r4.remove();
all.splice(all.indexOf(r4), 1);
gl.removeColumn(2);
gl.removeRow(1);
await record("removed");

i1.resize(150, 60);
await record("deepChildResized");

const freed = inner.flex;
inner.flex.remove();
await record("layoutRemoved");

return {
  waits,
  flexAfterRemove: inner.flex ? "still there" : null,
  freedLayoutType: typeof freed,
  tracks: { columns: gl.columns, rows: gl.rows },
  cells: Object.fromEntries([g1, g2, g3, g4, gAdded].map((s) => [s.name, s.layoutCell && {
    row: s.layoutCell.row, column: s.layoutCell.column, rowSpan: s.layoutCell.rowSpan, columnSpan: s.layoutCell.columnSpan,
  }])),
  steps,
};
