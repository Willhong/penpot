// PEN-11 scenario: hierarchy, transforms, paths and booleans. Groups and
// ungroups, clones, moves shapes between parents (also into a rotated board),
// reorders, aligns and distributes, rotates and flips, sets constraints,
// masks, edits path content, makes every boolean kind and flattens. Returns
// the resulting tree with geometry. Runs unchanged in a browser workspace and
// in the server-side executor (dual_run.py); every shape is named.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};

const rect = (name, x, y, width, height, color, parent) => {
  const shape = named(penpot.createRectangle(), name);
  if (parent) {
    parent.appendChild(shape);
  }
  shape.x = x;
  shape.y = y;
  shape.resize(width, height);
  shape.fills = [{ fillColor: color, fillOpacity: 1 }];
  return shape;
};

const board = named(penpot.createBoard(), "board");
board.x = 0;
board.y = 0;
board.resize(1200, 900);
board.fills = [{ fillColor: "#ffffff", fillOpacity: 1 }];

// transforms and constraints
const a = rect("a", 20, 20, 100, 80, "#e03131", board);
const b = rect("b", 160, 40, 120, 60, "#1971c2", board);
const c = rect("c", 320, 30, 80, 80, "#2f9e44", board);
const e = named(penpot.createEllipse(), "e");
board.appendChild(e);
e.x = 440;
e.y = 30;
e.resize(90, 60);
b.rotate(30);
c.rotation = 45;
c.flipX = true;
e.flipY = true;
e.rotate(15, { x: 400, y: 100 });
a.constraintsHorizontal = "leftright";
a.constraintsVertical = "bottom";
b.constraintsHorizontal = "center";
c.constraintsVertical = "scale";

// clone, and move into a rotated board: the clone keeps its place on the page
const inner = named(penpot.createBoard(), "inner");
board.appendChild(inner);
inner.x = 600;
inner.y = 300;
inner.resize(400, 300);
inner.fills = [{ fillColor: "#fff3bf", fillOpacity: 1 }];
inner.rotate(10);
const a2 = named(a.clone(), "a2");
a2.x = 650;
a2.y = 350;
inner.appendChild(a2);
const b2 = named(b.clone(), "b2");
inner.insertChild(0, b2);

// groups, nested groups, ungroup
const g = named(penpot.group([b, c]), "g");
const g2 = named(penpot.group([g, e]), "g2");
const loose1 = rect("loose1", 40, 500, 50, 50, "#868e96", board);
const loose2 = rect("loose2", 120, 520, 50, 50, "#495057", board);
const tmp = named(penpot.group([loose1, loose2]), "tmp");
penpot.ungroup(tmp);

// z-order
a.bringToFront();
loose1.sendToBack();
loose2.bringForward();
a.sendBackward();
c.setParentIndex(0);

// align and distribute
const row = [rect("r1", 40, 650, 40, 40, "#f08c00", board),
             rect("r2", 150, 680, 60, 30, "#f08c00", board),
             rect("r3", 400, 640, 30, 70, "#f08c00", board)];
penpot.alignVertical(row, "center");
penpot.distributeHorizontal(row);
const column = [rect("k1", 1000, 40, 40, 40, "#5f3dc4", board),
                rect("k2", 1020, 150, 60, 30, "#5f3dc4", board),
                rect("k3", 990, 400, 30, 70, "#5f3dc4", board)];
penpot.alignHorizontal(column, "right");
penpot.distributeVertical(column);

// masks
const masked = rect("masked", 600, 650, 150, 100, "#d6336c", board);
const maskShape = named(penpot.createEllipse(), "maskShape");
board.appendChild(maskShape);
maskShape.x = 620;
maskShape.y = 640;
maskShape.resize(100, 120);
const maskGroup = named(penpot.group([masked, maskShape]), "maskGroup");
maskGroup.makeMask();
const unmasked1 = rect("unmasked1", 800, 650, 80, 80, "#0c8599", board);
const unmasked2 = rect("unmasked2", 820, 670, 80, 80, "#66a80f", board);
const unmaskGroup = named(penpot.group([unmasked1, unmasked2]), "unmaskGroup");
unmaskGroup.makeMask();
unmaskGroup.removeMask();

// path content, as `d` and as commands (the setter takes the long command names only;
// the short ones the type declarations mention are refused, see pen11_refusals.js)
const path = named(penpot.createPath(), "path");
board.appendChild(path);
path.d = "M 0 0 L 120 0 L 120 80 C 80 120 40 120 0 80 Z";
path.x = 40;
path.y = 760;
path.strokes = [{ strokeColor: "#000000", strokeOpacity: 1, strokeStyle: "solid", strokeWidth: 2, strokeAlignment: "center" }];
const path2 = named(penpot.createPath(), "path2");
board.appendChild(path2);
path2.commands = [
  { command: "move-to", params: { x: 0, y: 0 } },
  { command: "line-to", params: { x: 60, y: 10 } },
  { command: "curve-to", params: { c1x: 90, c1y: 20, c2x: 90, c2y: 60, x: 60, y: 80 } },
  { command: "line-to", params: { x: 0, y: 70 } },
  { command: "close-path" },
];
path2.x = 200;
path2.y = 760;
path2.rotate(20);

// booleans of every kind, and flatten
const bools = {};
let x = 320;
for (const kind of ["union", "difference", "intersection", "exclude"]) {
  const first = rect(`${kind}-1`, x, 760, 70, 70, "#1098ad", board);
  const second = named(penpot.createEllipse(), `${kind}-2`);
  board.appendChild(second);
  second.x = x + 30;
  second.y = 790;
  second.resize(70, 70);
  bools[kind] = named(penpot.createBoolean(kind, [first, second]), `bool-${kind}`);
  x += 120;
}
const toFlatten = named(penpot.createEllipse(), "toFlatten");
board.appendChild(toFlatten);
toFlatten.x = 820;
toFlatten.y = 780;
toFlatten.resize(60, 40);
const flatRect = rect("flatRect", 900, 780, 50, 50, "#e8590c", board);
flatRect.rotate(25);
const flattened = penpot.flatten([toFlatten, flatRect]).map((shape, i) => named(shape, `flat-${i}`));

const geometry = (shape) => ({
  name: shape.name,
  type: shape.type,
  x: shape.x,
  y: shape.y,
  parentX: shape.parentX,
  parentY: shape.parentY,
  width: shape.width,
  height: shape.height,
  rotation: shape.rotation,
  flipX: shape.flipX,
  flipY: shape.flipY,
  constraints: [shape.constraintsHorizontal, shape.constraintsVertical],
  mask: shape.type === "group" ? shape.isMask() : undefined,
  children: shape.children ? shape.children.map(geometry) : undefined,
});

return {
  tree: geometry(board),
  pathD: path.toD(),
  path2Commands: path2.commands,
  boolD: Object.fromEntries(Object.entries(bools).map(([kind, shape]) => [kind, shape ? shape.toD() : null])),
  flattened: flattened.map((shape) => [shape.name, shape.type, shape.toD()]),
  parents: Object.fromEntries([a2, b2, b, e, loose1, loose2, masked].map((s) => [s.name, s.parent ? s.parent.name : null])),
};
