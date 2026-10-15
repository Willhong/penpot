// PEN-17 scenario: prototype data. Creates boards, flows and interactions of
// every action kind with animations, edits and removes some, adds ruler and
// board guides, then removes a board that interactions and a flow point to.
// Returns what the getters read back. Runs unchanged in a browser workspace and
// in the server-side executor (dual_run.py); every shape is named.

const named = (shape, name) => {
  shape.name = name;
  return shape;
};
const board = (name, x, color) => {
  const b = named(penpot.createBoard(), name);
  b.x = x;
  b.y = 0;
  b.resize(200, 300);
  b.fills = [{ fillColor: color, fillOpacity: 1 }];
  return b;
};
const home = board("Home", 0, "#f1f3f5");
const detail = board("Detail", 300, "#e7f5ff");
const overlay = board("Overlay", 600, "#fff3bf");
overlay.resize(160, 100);
const extra = board("Extra", 900, "#ebfbee");
const button = named(penpot.createRectangle(), "button");
home.appendChild(button);
button.x = 20;
button.y = 240;
button.resize(160, 40);
const back = named(penpot.createRectangle(), "back");
detail.appendChild(back);
back.x = 320;
back.y = 20;
back.resize(40, 40);
const close = named(penpot.createRectangle(), "close");
overlay.appendChild(close);
close.x = 610;
close.y = 10;
close.resize(20, 20);

// interactions of every action kind
const toDetail = button.addInteraction("click", {
  type: "navigate-to", destination: detail, preserveScrollPosition: true,
  animation: { type: "slide", way: "in", direction: "left", duration: 300, offsetEffect: true, easing: "ease-in-out" },
});
home.addInteraction("after-delay", {
  type: "open-overlay", destination: overlay, position: "center", closeWhenClickOutside: true,
  addBackgroundOverlay: true, animation: { type: "dissolve", duration: 200, easing: "linear" },
}, 1500);
button.addInteraction("mouse-enter", { type: "toggle-overlay", destination: overlay, position: "bottom-right" });
close.addInteraction("click", { type: "close-overlay", animation: { type: "dissolve", duration: 100, easing: "ease-out" } });
back.addInteraction("click", { type: "previous-screen" });
detail.addInteraction("mouse-leave", { type: "open-url", url: "https://penpot.app" });
const toExtra = back.addInteraction("click", {
  type: "navigate-to", destination: extra, animation: { type: "push", direction: "up", duration: 400, easing: "ease" },
});

// editing and removing interactions
toDetail.trigger = "mouse-enter";
toDetail.trigger = "click";
toExtra.trigger = "mouse-leave";
const delayed = extra.addInteraction("after-delay", { type: "navigate-to", destination: home }, 2000);
delayed.delay = 600;
const removed = back.addInteraction("click", { type: "open-url", url: "https://example.com" });
removed.remove();

// flows
// the first navigation made a flow from its board already; a board starts one flow at most
const page = penpot.currentPage;
const autoFlows = page.flows.map((f) => ({ name: f.name, start: f.startingBoard ? f.startingBoard.name : null }));
const starts = () => page.flows.map((f) => f.startingBoard && f.startingBoard.id);
const free = () => [home, detail, overlay, extra].filter((b) => !starts().includes(b.id));
const secondary = page.createFlow("Secondary", free()[0]);
const doomed = page.createFlow("Doomed", free()[0]);
if (page.flows[0]) {
  page.flows[0].name = "Main flow";
}
secondary.startingBoard = extra;
page.removeFlow(doomed);

// guides
const h = page.addRulerGuide("horizontal", 350);
const v = page.addRulerGuide("vertical", 150);
v.position = 175;
const onBoard = home.addRulerGuide("horizontal", 120);
const gone = page.addRulerGuide("vertical", 999);
gone.remove();
home.guides = [
  { type: "column", display: true, params: { color: { color: "#ff0000", opacity: 0.2 }, type: "stretch", size: 4, margin: 10, gutter: 8 } },
  { type: "square", display: false, params: { color: { color: "#0000ff", opacity: 0.1 }, size: 16 } },
];

const readInteractions = (shape) =>
  shape.interactions.map((i) => ({
    trigger: i.trigger,
    delay: i.delay,
    action: {
      type: i.action.type,
      destination: i.action.destination ? i.action.destination.name : null,
      position: i.action.position || null,
      url: i.action.url || null,
      animation: i.action.animation ? { ...i.action.animation } : null,
      preserveScrollPosition: i.action.preserveScrollPosition ?? null,
      closeWhenClickOutside: i.action.closeWhenClickOutside ?? null,
      addBackgroundOverlay: i.action.addBackgroundOverlay ?? null,
    },
  }));
const snapshot = () => ({
  interactions: Object.fromEntries([home, detail, overlay, button, back, close].map((s) => [s.name, readInteractions(s)])),
  flows: page.flows.map((f) => ({ name: f.name, start: f.startingBoard ? f.startingBoard.name : null })),
  rulerGuides: page.rulerGuides.map((g) => ({ orientation: g.orientation, position: g.position, board: g.board ? g.board.name : null })),
  boardGuides: home.guides.map((g) => ({ type: g.type, display: g.display, params: g.params })),
});
const before = snapshot();

// a removed board that interactions and a flow point to
extra.remove();
await penpot.waitForLayoutUpdate(10000);
const after = snapshot();

return { autoFlows, before, after, guideIds: [h.orientation, onBoard.board ? onBoard.board.name : null] };
