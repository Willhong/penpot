// PEN-11 refusals: structural edits that must be refused or ignored the same
// way in a browser workspace and in the server-side executor (dual_run.py):
// parent cycles, invalid paths and boolean kinds, out-of-range indices and
// invalid transforms. Returns each attempt's outcome and the tree left behind.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};

const outer = named(penpot.createBoard(), "outer");
outer.resize(500, 400);
const nested = named(penpot.createBoard(), "nested");
outer.appendChild(nested);
nested.resize(200, 200);
const r = named(penpot.createRectangle(), "r");
nested.appendChild(r);
const s = named(penpot.createRectangle(), "s");
outer.appendChild(s);
s.x = 300;
const path = named(penpot.createPath(), "path");
outer.appendChild(path);
path.d = "M 0 0 L 10 10";

const attempt = (fn) => {
  try {
    const value = fn();
    return { ok: true, value: value === undefined ? null : value && value.name ? value.name : value };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
};

const outcomes = {
  appendSelf: attempt(() => outer.appendChild(outer)),
  appendAncestor: attempt(() => nested.appendChild(outer)),
  insertAncestor: attempt(() => nested.insertChild(0, outer)),
  insertBadIndex: attempt(() => outer.insertChild(99, r)),
  setParentIndexNegative: attempt(() => s.setParentIndex(-1)),
  groupEmpty: attempt(() => penpot.group([])),
  ungroupNotGroup: attempt(() => penpot.ungroup(s)),
  booleanBadKind: attempt(() => penpot.createBoolean("merge", [r, s])),
  booleanOneShape: attempt(() => penpot.createBoolean("union", [s])),
  booleanNone: attempt(() => penpot.createBoolean("union", [])),
  pathGarbage: attempt(() => {
    path.d = "this is not a path";
  }),
  pathBadCommand: attempt(() => {
    path.commands = [{ command: "X", params: { x: 1 } }];
  }),
  pathShortNames: attempt(() => {
    path.commands = [
      { command: "M", params: { x: 0, y: 0 } },
      { command: "L", params: { x: 6, y: 8 } },
    ];
  }),
  pathQuadratic: attempt(() => {
    path.commands = [
      { command: "move-to", params: { x: 0, y: 0 } },
      { command: "quadratic-bezier-curve-to", params: { x1: 9, y1: 4, x: 6, y: 8 } },
    ];
  }),
  rotateNaN: attempt(() => s.rotate(NaN)),
  rotationString: attempt(() => {
    s.rotation = "ninety";
  }),
  flipNumber: attempt(() => {
    s.flipX = 1;
  }),
  constraintBad: attempt(() => {
    s.constraintsHorizontal = "middle";
  }),
  alignBad: attempt(() => penpot.alignHorizontal([r, s], "middle")),
  flattenNone: attempt(() => penpot.flatten([]).length),
  makeMaskOnRect: attempt(() => s.makeMask && s.makeMask()),
};

const tree = (shape) => ({
  name: shape.name,
  x: shape.x,
  y: shape.y,
  rotation: shape.rotation,
  flipX: shape.flipX,
  constraints: [shape.constraintsHorizontal, shape.constraintsVertical],
  d: shape.type === "path" ? shape.toD() : undefined,
  children: shape.children ? shape.children.map(tree) : undefined,
});

return { outcomes, tree: tree(outer) };
