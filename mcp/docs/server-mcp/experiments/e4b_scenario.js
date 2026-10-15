// E4b scenario: edits the shapes `e4_scenario.js` saved, after the file was
// reopened, so the engine computes from shapes loaded from the backend
// rather than from shapes created in the same session.

const byName = (name) => penpot.currentPage.findShapes().find((s) => s.name === name);

// flex reflow: narrower board, reversed direction, wider gaps
const board = byName("flex-board");
board.resize(200, 300);
board.flex.dir = "row-reverse";
board.flex.columnGap = 16;

// text: new content for the auto-width text, larger size for the flex text
byName("text-auto-width").characters = "Reopened 서버 편집 0123456789";
byName("flex-text").fontSize = "30";

// boolean: move one operand of the union and change the difference type
const union = byName("bool-union");
const ellipse = union.children.find((s) => s.name === "bool-union-ellipse");
ellipse.x = ellipse.x + 30;

await penpot.waitForLayoutUpdate(5000).catch(() => null);
return penpot.currentPage.findShapes().length;
