// PEN-13 refusals: invalid layout values must be refused or ignored the same
// way in a browser workspace and in the server-side executor (dual_run.py).
// Returns each attempt's outcome and the layout left behind.

const board = penpot.createBoard();
board.name = "board";
board.resize(300, 200);
const flex = board.addFlexLayout();
const child = penpot.createRectangle();
child.name = "child";
flex.appendChild(child);
const gridBoard = penpot.createBoard();
gridBoard.name = "gridBoard";
gridBoard.x = 400;
const grid = gridBoard.addGridLayout();
grid.addColumn("flex", 1);
grid.addRow("flex", 1);
const cell = penpot.createRectangle();
cell.name = "cell";
grid.appendChild(cell, 1, 1);

const attempt = (fn) => {
  try {
    const value = fn();
    return { ok: true, value: value === undefined ? null : value };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
};

const outcomes = {
  dirBad: attempt(() => {
    flex.dir = "diagonal";
  }),
  wrapBad: attempt(() => {
    flex.wrap = "sometimes";
  }),
  gapNegative: attempt(() => {
    flex.rowGap = -5;
  }),
  gapText: attempt(() => {
    flex.columnGap = "wide";
  }),
  paddingNaN: attempt(() => {
    flex.topPadding = NaN;
  }),
  alignBad: attempt(() => {
    flex.alignItems = "middle";
  }),
  sizingBad: attempt(() => {
    flex.horizontalSizing = "grow";
  }),
  childSizingBad: attempt(() => {
    child.layoutChild.horizontalSizing = "grow";
  }),
  childMaxText: attempt(() => {
    child.layoutChild.maxWidth = "big";
  }),
  childZIndexText: attempt(() => {
    child.layoutChild.zIndex = "top";
  }),
  trackTypeBad: attempt(() => grid.addColumn("stretchy", 1)),
  trackValueText: attempt(() => grid.addRow("fixed", "tall")),
  removeColumnOutOfRange: attempt(() => grid.removeColumn(9)),
  setRowOutOfRange: attempt(() => grid.setRow(9, "fixed", 10)),
  appendCellOutOfRange: attempt(() => {
    const extra = penpot.createRectangle();
    extra.name = "extra";
    grid.appendChild(extra, 9, 9);
    return extra.parent ? extra.parent.name : null;
  }),
  spanZero: attempt(() => {
    cell.layoutCell.rowSpan = 0;
  }),
  positionBad: attempt(() => {
    cell.layoutCell.position = "floating";
  }),
  addFlexTwice: attempt(() => {
    board.addFlexLayout();
    return board.flex ? board.flex.dir : null;
  }),
  addGridToRect: attempt(() => child.addGridLayout && child.addGridLayout()),
};

return {
  outcomes,
  flex: {
    dir: flex.dir,
    wrap: flex.wrap,
    rowGap: flex.rowGap,
    columnGap: flex.columnGap,
    topPadding: flex.topPadding,
    alignItems: flex.alignItems,
    horizontalSizing: flex.horizontalSizing,
  },
  child: { sizing: child.layoutChild.horizontalSizing, maxWidth: child.layoutChild.maxWidth, zIndex: child.layoutChild.zIndex },
  grid: { columns: grid.columns, rows: grid.rows, cell: { rowSpan: cell.layoutCell.rowSpan, position: cell.layoutCell.position } },
};
