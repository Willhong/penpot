// PEN-17 refusals: invalid prototype data must be refused the same way in a
// browser workspace and in the server-side executor (dual_run.py). Returns each
// attempt's outcome and what is left.

const board = penpot.createBoard();
board.name = "A";
const other = penpot.createBoard();
other.name = "B";
other.x = 300;
const rect = penpot.createRectangle();
rect.name = "rect";
board.appendChild(rect);
const gone = penpot.createBoard();
gone.name = "Gone";
gone.x = 600;
const page = penpot.currentPage;

const attempt = (fn) => {
  try {
    const value = fn();
    return { ok: true, value: value === undefined ? null : value && value.name !== undefined ? value.name : value };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error).slice(0, 200) };
  }
};

const outcomes = {
  triggerBad: attempt(() => rect.addInteraction("double-click", { type: "navigate-to", destination: other })),
  actionBad: attempt(() => rect.addInteraction("click", { type: "teleport", destination: other })),
  destinationNotBoard: attempt(() => rect.addInteraction("click", { type: "navigate-to", destination: rect })),
  destinationOwnBoard: attempt(() => rect.addInteraction("click", { type: "navigate-to", destination: board })),
  urlEmpty: attempt(() => rect.addInteraction("click", { type: "open-url", url: "" })),
  delayOnShape: attempt(() => rect.addInteraction("after-delay", { type: "navigate-to", destination: other }, 100)),
  delayNegative: attempt(() => board.addInteraction("after-delay", { type: "navigate-to", destination: other }, -5)),
  pushOnOverlay: attempt(() => rect.addInteraction("click", { type: "open-overlay", destination: other, animation: { type: "push", direction: "up", duration: 100, easing: "linear" } })),
  durationText: attempt(() => rect.addInteraction("click", { type: "navigate-to", destination: other, animation: { type: "dissolve", duration: "slow", easing: "linear" } })),
  flowNameEmpty: attempt(() => page.createFlow("", other)),
  flowNotBoard: attempt(() => page.createFlow("F", rect)),
  guideOrientationBad: attempt(() => page.addRulerGuide("diagonal", 10)),
  guidePositionText: attempt(() => page.addRulerGuide("vertical", "ten")),
  boardGuideBad: attempt(() => {
    board.guides = [{ type: "hexagon", display: true, params: {} }];
  }),
};
const toGone = attempt(() => rect.addInteraction("click", { type: "navigate-to", destination: gone }));
gone.remove();
outcomes.afterDestinationRemoved = attempt(() => rect.interactions.map((i) => [i.trigger, i.action.type, i.action.destination ? i.action.destination.name : null]));
outcomes.toGone = toGone;
await penpot.waitForLayoutUpdate(10000);
return {
  outcomes,
  interactions: rect.interactions.length,
  flows: page.flows.map((f) => f.name),
  guides: page.rulerGuides.length,
  boardGuides: board.guides.length,
};
