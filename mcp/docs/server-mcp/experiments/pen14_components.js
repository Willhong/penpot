// PEN-14 scenario: components in one file. Creates a component, places three
// instances, overrides two of them, changes the main so the change propagates,
// nests an instance in another component, detaches, swaps, resets overrides,
// makes variants (properties, values, switching, combining) and removes a
// referenced main. Waits for the component sync after each step and returns
// what every instance reads back. Runs unchanged in a browser workspace and in
// the server-side executor (dual_run.py); every shape is named.

const named = (shape, name) => {
  shape.name = name;
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

const child = (shape, name) => shape.children.find((c) => c.name === name);
const fill = (shape) => (shape && shape.fills.length ? shape.fills[0].fillColor : null);
const read = (shape) =>
  shape && {
    name: shape.name,
    type: shape.type,
    x: shape.x,
    y: shape.y,
    width: shape.width,
    height: shape.height,
    instance: shape.isComponentInstance(),
    main: shape.isComponentMainInstance(),
    copy: shape.isComponentCopyInstance(),
    root: shape.isComponentRoot(),
    component: shape.component() ? shape.component().name : null,
    children: shape.children
      ? shape.children.map((c) => ({ name: c.name, fill: fill(c), hidden: c.hidden, x: c.x, y: c.y, w: c.width }))
      : undefined,
  };
const steps = {};

// --- a component with three instances
const card = named(penpot.createBoard(), "Card");
card.resize(160, 100);
card.fills = [{ fillColor: "#ffffff", fillOpacity: 1 }];
const bg = named(penpot.createRectangle(), "bg");
card.appendChild(bg);
bg.resize(140, 40);
bg.x = 10;
bg.y = 10;
bg.fills = [{ fillColor: "#adb5bd", fillOpacity: 1 }];
const dot = named(penpot.createEllipse(), "dot");
card.appendChild(dot);
dot.resize(20, 20);
dot.x = 20;
dot.y = 60;
const comp = penpot.library.local.createComponent([card]);
comp.name = "Card";
await settle("created");
const main = comp.mainInstance();
const instances = [1, 2, 3].map((n) => {
  const inst = named(comp.instance(), `card-${n}`);
  inst.x = 200 * n;
  inst.y = 0;
  return inst;
});
await settle("instanced");

// overrides on two copies
child(instances[1], "bg").fills = [{ fillColor: "#e03131", fillOpacity: 1 }];
child(instances[2], "dot").hidden = true;
await settle("overridden");

// a change of the main: unchanged copies follow, overridden properties stay
child(main, "bg").fills = [{ fillColor: "#1971c2", fillOpacity: 1 }];
child(main, "dot").x = main.x + 120;
const badge = named(penpot.createRectangle(), "badge");
main.appendChild(badge);
badge.resize(10, 10);
badge.x = main.x + 140;
badge.y = main.y + 5;
await settle("mainChanged");
steps.afterMainChange = instances.map(read);

// a nested instance: a component that holds a Card copy
const panel = named(penpot.createBoard(), "Panel");
panel.resize(220, 140);
panel.x = 0;
panel.y = 300;
const nested = named(comp.instance(), "nested-card");
panel.appendChild(nested);
nested.x = panel.x + 10;
nested.y = panel.y + 10;
const panelComp = penpot.library.local.createComponent([panel]);
panelComp.name = "Panel";
const panelCopy = named(panelComp.instance(), "panel-copy");
panelCopy.x = 300;
panelCopy.y = 300;
await settle("nested");
child(main, "bg").fills = [{ fillColor: "#2f9e44", fillOpacity: 1 }];
await settle("mainChangedAgain");
steps.nested = {
  panelMain: read(panelComp.mainInstance()),
  panelCopy: read(panelCopy),
  nestedInCopy: read(panelCopy.children[0]),
};

// detach, swap, reset overrides
const other = named(penpot.createEllipse(), "Other");
other.resize(60, 60);
other.x = 0;
other.y = 600;
const otherComp = penpot.library.local.createComponent([other]);
otherComp.name = "Other";
await settle("otherComponent");
instances[2].detach();
const swapped = instances[0];
swapped.swapComponent(otherComp);
instances[1].resetOverrides();
await settle("detachSwapReset");
steps.detachSwapReset = {
  detached: read(instances[2]),
  swapped: penpot.currentPage
    .findShapes()
    .filter((s) => s.isComponentCopyInstance() && s.isComponentRoot() && s.component() && s.component().name === "Other")
    .map(read),
  reset: read(instances[1]),
};

// variants
const button = named(penpot.createBoard(), "Button");
button.resize(100, 32);
button.x = 600;
button.y = 300;
button.fills = [{ fillColor: "#5f3dc4", fillOpacity: 1 }];
const buttonComp = penpot.library.local.createComponent([button]);
buttonComp.name = "Button";
await settle("button");
buttonComp.transformInVariant();
await settle("transformed");
const variantComps = () => (buttonComp.isVariant() && buttonComp.variants ? buttonComp.variants.variantComponents() : []);
const variants = buttonComp.variants;
if (variants) {
  variants.addProperty();
  variants.renameProperty(0, "Size");
  variants.renameProperty(1, "State");
  buttonComp.setVariantProperty(0, "small");
  buttonComp.setVariantProperty(1, "default");
  variants.addVariant();
  await settle("variantAdded");
  const second = variantComps().find((c) => c.id !== buttonComp.id);
  if (second) {
    second.setVariantProperty(0, "large");
    second.setVariantProperty(1, "hover");
  }
}
await settle("variantProps");
const buttonCopy = named(buttonComp.instance(), "button-copy");
buttonCopy.x = 600;
buttonCopy.y = 500;
await settle("variantInstance");
let switched = null;
try {
  buttonCopy.switchVariant(0, "large");
  switched = "ok";
} catch (error) {
  switched = String(error.message || error);
}
await settle("switched");
const switchedCopy = penpot.currentPage.findShapes({ name: "button-copy" })[0] ||
  penpot.currentPage.findShapes().find((s) => s.isComponentCopyInstance() && s.y === 500 && s.x === 600);
steps.variants = {
  isVariant: buttonComp.isVariant(),
  properties: variants ? variants.properties : null,
  values: variants ? variants.properties.map((p) => [p, variants.currentValues(p)]) : null,
  components: variantComps().map((c) => ({ name: c.name, props: c.variantProps })),
  switched,
  copy: switchedCopy ? { component: switchedCopy.component() && switchedCopy.component().name,
                         props: switchedCopy.component() && switchedCopy.component().variantProps } : null,
};

// two plain components combined as variants
const chipA = named(penpot.createRectangle(), "ChipA");
chipA.x = 900;
chipA.y = 300;
const chipB = named(penpot.createRectangle(), "ChipB");
chipB.x = 1000;
chipB.y = 300;
const chipAComp = penpot.library.local.createComponent([chipA]);
const chipBComp = penpot.library.local.createComponent([chipB]);
await settle("chips");
let combined = null;
try {
  const container = chipAComp.mainInstance().combineAsVariants([chipBComp.mainInstance().id]);
  combined = container ? { name: container.name, variant: container.isVariantContainer() } : null;
} catch (error) {
  combined = String(error.message || error);
}
await settle("combined");

// removing a referenced main: copies stay, with their own shapes
const orphanComp = penpot.library.local.createComponent([named(penpot.createRectangle(), "Orphan")]);
orphanComp.name = "Orphan";
const orphanCopy = named(orphanComp.instance(), "orphan-copy");
orphanCopy.x = 1200;
await settle("orphanInstance");
orphanComp.mainInstance().remove();
await settle("mainRemoved");

return {
  waits,
  steps,
  combined,
  orphan: read(penpot.currentPage.findShapes({ name: "orphan-copy" })[0]),
  components: penpot.library.local.components.map((c) => ({ name: c.name, path: c.path, variant: c.isVariant() })).sort((a, b) => a.name.localeCompare(b.name)),
};
