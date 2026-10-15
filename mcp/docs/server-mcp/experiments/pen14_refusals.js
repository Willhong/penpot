// PEN-14 refusals: invalid component and variant operations must be refused
// or ignored the same way in a browser workspace and in the server-side
// executor (dual_run.py). Returns each attempt's outcome and what is left.

const rect = penpot.createRectangle();
rect.name = "plain";
const source = penpot.createRectangle();
source.name = "Source";
source.x = 200;
const comp = penpot.library.local.createComponent([source]);
comp.name = "Source";
await penpot.waitForLayoutUpdate(10000);
const copy = comp.instance();
copy.name = "copy";
copy.x = 400;
await penpot.waitForLayoutUpdate(10000);

const attempt = (fn) => {
  try {
    const value = fn();
    return { ok: true, value: value === undefined ? null : value && value.name !== undefined ? value.name : value };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
};

const outcomes = {
  createEmpty: attempt(() => penpot.library.local.createComponent([])),
  createFromNonShapes: attempt(() => penpot.library.local.createComponent([{ id: "x" }])),
  swapToPlainShape: attempt(() => copy.swapComponent(rect)),
  swapOnPlainShape: attempt(() => rect.swapComponent(comp)),
  detachPlainShape: attempt(() => rect.detach()),
  resetPlainShape: attempt(() => rect.resetOverrides()),
  switchVariantNotVariant: attempt(() => copy.switchVariant(0, "large")),
  setVariantPropertyNotVariant: attempt(() => comp.setVariantProperty && comp.setVariantProperty(0, "x")),
  combineWithPlainShape: attempt(() => comp.mainInstance().combineAsVariants([rect.id])),
  combineWithGarbage: attempt(() => comp.mainInstance().combineAsVariants(["not-an-id"])),
  componentOfPlain: attempt(() => rect.component()),
  nameEmpty: attempt(() => {
    comp.name = "";
  }),
  pathNumber: attempt(() => {
    comp.path = 42;
  }),
};
let connect;
try {
  await penpot.library.connectLibrary("not-a-library-id");
  connect = { ok: true };
} catch (error) {
  connect = { ok: false, error: String(error && error.message ? error.message : error) };
}
outcomes.connectGarbage = connect;
await penpot.waitForLayoutUpdate(10000);

return {
  outcomes,
  copy: { instance: copy.isComponentInstance(), component: copy.component() && copy.component().name },
  plain: { instance: rect.isComponentInstance() },
  components: penpot.library.local.components.map((c) => [c.name, c.path]),
};
