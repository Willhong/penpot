// PEN-9 integrated scenario: features that depend on each other in one file.
// Design tokens and library assets style a button component whose label sits
// in a hugging flex layout; the button becomes a variant set; a card lays out
// a library-styled text in two scripts, an image fill, a button copy and a
// boolean in a flex column; a grid holds four more copies; a copy navigates
// to another board. Then token values, the main component's label and one
// copy's variant change, so token propagation, component sync, text
// measuring and nested reflow all run again. Returns what the getters read
// after each stage. Runs unchanged in a browser workspace and in the
// server-side executor (pen9_integrated.py); every shape is named.

const IMAGE = "__PNG_BASE64__";

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
    // in a browser, which layout work is still pending (diagnosis; the server has no `app`)
    const pending = typeof app === "undefined" ? null : (() => {
      const objects = app.main.data.helpers.lookup_page_objects(cljs.core.deref(app.main.store.state));
      return cljs.core.into_array(cljs.core.map((e) => {
        const o = cljs.core.get(objects, cljs.core.key(e));
        return [o ? cljs.core.get(o, cljs.core.keyword("name")) : String(cljs.core.key(e)), cljs.core.pr_str(cljs.core.val(e))];
      }, app.main.data.workspace.reflow.pending_shapes.getValue()));
    })();
    waits.push(pending ? [label, String(error.message || error), pending] : [label, String(error.message || error)]);
  }
};
const round = (n) => (typeof n === "number" ? Math.round(n * 100) / 100 : n);
const box = (s) => [round(s.x), round(s.y), round(s.width), round(s.height)];
const child = (shape, name) => shape.children.find((c) => c.name === name);
const lib = penpot.library.local;

// --- tokens and library assets
const tokens = lib.tokens;
const brand = tokens.addSet({ name: "brand", active: true });
const t = {
  primary: brand.addToken({ type: "color", name: "color.primary", value: "#5F3DC4" }),
  onPrimary: brand.addToken({ type: "color", name: "color.on-primary", value: "#FFFFFF" }),
  space: brand.addToken({ type: "spacing", name: "space.base", value: "8" }),
  gap: brand.addToken({ type: "spacing", name: "space.gap", value: "{space.base} * 1.5" }),
  radius: brand.addToken({ type: "borderRadius", name: "radius.button", value: "6" }),
  label: brand.addToken({ type: "fontSizes", name: "font.label", value: "14" }),
};
const ink = lib.createColor();
ink.name = "Ink";
ink.color = "#212529";
const heading = lib.createTypography();
heading.name = "Heading";
heading.fontSize = "20";
heading.fontWeight = "700";
heading.lineHeight = "1.2";
await settle("assets");

// --- a button: a hugging flex board with a label, styled by tokens
const button = named(penpot.createBoard(), "button");
button.x = 800;
button.y = 0;
const buttonFlex = button.addFlexLayout();
buttonFlex.dir = "row";
buttonFlex.alignItems = "center";
const label = named(penpot.createText("Buy 구매하기"), "label");
buttonFlex.appendChild(label);
await settle("buttonBuilt");
button.horizontalSizing = "auto";
button.verticalSizing = "auto";
t.primary.applyToShapes([button], ["fill"]);
t.radius.applyToShapes([button]);
t.space.applyToShapes([button], ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"]);
t.label.applyToShapes([label]);
t.onPrimary.applyToShapes([label], ["fill"]);
await settle("buttonTokens");

// --- the button as a component with two variants
const buttonComp = lib.createComponent([button]);
buttonComp.name = "Button";
await settle("component");
buttonComp.transformInVariant();
await settle("variant");
const variants = buttonComp.variants;
variants.renameProperty(0, "Size");
buttonComp.setVariantProperty(0, "large");
variants.addVariant();
await settle("variantAdded");
const small = variants.variantComponents().find((c) => c.id !== buttonComp.id);
small.setVariantProperty(0, "small");
child(small.mainInstance(), "label").fontSize = "11";
await settle("variants");

// --- a card: a flex column with a library-styled text, an image, a copy and a boolean
const card = named(penpot.createBoard(), "card");
card.resize(320, 100);
card.fills = [{ fillColor: "#FFFFFF", fillOpacity: 1 }];
const cardFlex = card.addFlexLayout();
cardFlex.dir = "column";
cardFlex.horizontalPadding = 16;
cardFlex.verticalPadding = 16;
const title = named(penpot.createText("Weekly picks 이번 주 추천 상품을 확인하세요"), "title");
cardFlex.appendChild(title);
await settle("title");
heading.applyToText(title);
// a resize makes a text fixed, so the width comes first
title.resize(288, title.height);
title.growType = "auto-height";
const bytes = Uint8Array.from(atob(IMAGE), (c) => c.charCodeAt(0));
const image = await penpot.uploadMediaData("photo", bytes, "image/png");
const photo = named(penpot.createRectangle(), "photo");
cardFlex.appendChild(photo);
photo.resize(288, 120);
photo.borderRadius = 8;
photo.fills = [{ fillOpacity: 1, fillImage: image }];
const cta = named(buttonComp.instance(), "cta");
cardFlex.appendChild(cta);
const dotA = named(penpot.createEllipse(), "dot-a");
dotA.resize(24, 24);
const dotB = named(penpot.createEllipse(), "dot-b");
dotB.resize(24, 24);
dotB.x = dotA.x + 12;
const badge = named(penpot.createBoolean("union", [dotA, dotB]), "badge");
badge.fills = [ink.asFill()];
cardFlex.appendChild(badge);
await settle("cardBuilt");
card.verticalSizing = "auto";
t.gap.applyToShapes([card], ["rowGap"]);
await settle("card");

// --- a grid of four copies
const grid = named(penpot.createBoard(), "grid");
grid.x = 400;
grid.resize(320, 120);
const gridLayout = grid.addGridLayout();
gridLayout.addColumn("flex", 1);
gridLayout.addColumn("flex", 1);
gridLayout.addRow("auto");
gridLayout.addRow("auto");
gridLayout.rowGap = 8;
gridLayout.columnGap = 8;
const copies = [1, 2, 3, 4].map((n) => named(buttonComp.instance(), `copy-${n}`));
copies.forEach((copy, i) => gridLayout.appendChild(copy, Math.floor(i / 2) + 1, (i % 2) + 1));
await settle("grid");

// --- prototype: the card's button opens a detail board
const detail = named(penpot.createBoard(), "detail");
detail.x = 0;
detail.y = 600;
detail.resize(320, 200);
cta.addInteraction("click", { type: "navigate-to", destination: detail });
await settle("prototype");

const snapshot = () => {
  const copyState = (s) => ({
    box: box(s),
    fill: s.fills[0] && s.fills[0].fillColor,
    variant: s.component() && s.component().variantProps,
    label: (() => {
      const l = child(s, "label");
      return l && { text: l.characters, size: l.fontSize, box: box(l) };
    })(),
  });
  return {
    card: { box: box(card), children: card.children.map((c) => [c.name, ...box(c)]) },
    title: { box: box(title), font: [title.fontFamily, title.fontSize, title.fontWeight] },
    // a variant switch replaces the copy, so copies are found by place rather than by name
    cta: copyState(card.children.find((c) => c.isComponentCopyInstance())),
    grid: [...grid.children].sort((a, b) => a.y - b.y || a.x - b.x).map(copyState),
    tokens: Object.fromEntries(Object.entries(t).map(([k, token]) => [k, token.resolvedValueString])),
  };
};
const built = snapshot();

// --- changes that cross features
t.primary.value = "#1971C2";
t.space.value = "12";
t.label.value = "16";
await settle("tokensChanged");
child(buttonComp.mainInstance(), "label").characters = "Buy now 지금 구매";
await settle("mainChanged");
const fourth = penpot.currentPage.findShapes({ name: "copy-4" })[0];
fourth.switchVariant(0, "small");
await settle("switched");
const changed = snapshot();

return {
  waits,
  built,
  changed,
  library: {
    colors: lib.colors.map((c) => [c.name, c.color]),
    typographies: lib.typographies.map((x) => [x.name, x.fontSize, x.fontWeight]),
    components: lib.components.map((c) => [c.name, c.isVariant() ? c.variantProps : null]).sort(),
  },
  flows: penpot.currentPage.flows.map((f) => [f.name, f.startingBoard.name]),
  interactions: card.children.find((c) => c.isComponentCopyInstance()).interactions
    .map((i) => [i.trigger, i.action.type, i.action.destination && i.action.destination.name]),
};
