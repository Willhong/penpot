// PEN-9 gap scenario (2/3): component, library and token members no earlier
// scenario ran on the server. Variants made from components, component
// heads and roots, library names and element ids, a library color with an
// image, every token type with its value and resolved value, token, set and
// theme ids, duplicates and removal, and the value objects shapesColors and
// availableLibraries hand back. Ids are compared as "is it the same object",
// since each side makes its own. Runs unchanged in a browser workspace and in
// the server-side executor (pen9_gaps.py); every shape is named.

const IMAGE = "__PNG_BASE64__";

const named = (shape, name) => {
  shape.name = name;
  return shape;
};
const tryv = (f) => {
  try {
    const v = f();
    return v === undefined ? null : v;
  } catch (error) {
    return "ERR " + String(error.message || error);
  }
};
const settle = async () => {
  try {
    await penpot.waitForLayoutUpdate(10000);
    return "ok";
  } catch (error) {
    return String(error.message || error);
  }
};
const lib = penpot.library.local;
const out = {};

// --- components and variants
const boardA = named(penpot.createBoard(), "Chip");
boardA.resize(80, 30);
const boardB = named(penpot.createBoard(), "Tag");
boardB.resize(80, 30);
boardB.x = 120;
const compA = lib.createComponent([boardA]);
const compB = lib.createComponent([boardB]);
out.settle1 = await settle();
const container = tryv(() => penpot.createVariantFromComponents([compA.mainInstance(), compB.mainInstance()]));
out.settle2 = await settle();
out.container = typeof container === "string" ? container : container && [
  container.isVariantContainer(),
  container.variants && typeof container.variants.id === "string",
  container.variants && container.variants.libraryId === lib.id,
];
const variants = container && typeof container !== "string" ? container.variants : null;
if (variants) {
  const first = variants.variantComponents()[0];
  out.variantComponent = [first.isVariant(), typeof first.variantError, first.variantError];
  first.addVariant();
  out.settle3 = await settle();
  variants.addProperty();
  out.properties = variants.properties.slice();
  variants.removeProperty(variants.properties.length - 1);
  out.propertiesAfter = variants.properties.slice();
  out.variantCount = variants.variantComponents().length;
}
const inner = named(penpot.createRectangle(), "inner");
const outerBoard = named(penpot.createBoard(), "Outer");
outerBoard.y = 200;
outerBoard.appendChild(inner);
const outerComp = lib.createComponent([outerBoard]);
const copy = named(outerComp.instance(), "outer-copy");
copy.y = 400;
out.settle4 = await settle();
const innerCopy = copy.children[0];
out.heads = [copy.isComponentHead(), innerCopy.isComponentHead(),
  copy.componentHead() && copy.componentHead().name, innerCopy.componentHead() && innerCopy.componentHead().name,
  innerCopy.componentRoot() && innerCopy.componentRoot().name,
  innerCopy.componentRefShape() && innerCopy.componentRefShape().name,
  copy.isVariantHead(), compA.mainInstance().isVariantHead()];

// --- library names and elements
out.libraryName = typeof lib.name === "string";
const color = lib.createColor();
color.name = "Gap color";
color.color = "#7048E8";
out.colorLibrary = color.libraryId === lib.id;
const bytes = Uint8Array.from(atob(IMAGE), (c) => c.charCodeAt(0));
const image = await penpot.uploadMediaData("gap", bytes, "image/png");
out.imageData = [typeof image.id === "string", (await image.data()).length > 0];
const imageColor = lib.createColor();
imageColor.name = "Gap image";
imageColor.image = image;
out.libraryImage = imageColor.image ? [imageColor.image.width, imageColor.image.height] : null;

// --- value objects of shapesColors and availableLibraries
const painted = named(penpot.createRectangle(), "painted");
painted.y = 600;
painted.fills = [color.asFill()];
painted.strokes = [{ strokeColor: "#000000", strokeOpacity: 1, strokeWidth: 2, strokeStyle: "solid",
  strokeAlignment: "center" }];
out.settle5 = await settle();
out.shapesColors = penpot.shapesColors([painted]).map((c) => [c.color, c.opacity, c.name || null,
  c.path ?? null, c.id === color.id, c.fileId === color.fileId, c.refFile ? "ref" : null, c.gradient || null,
  c.image || null, (c.shapesInfo || []).map((e) => [e.property, e.index ?? null, e.shapeId === painted.id])]);
out.libraries = (await penpot.library.availableLibraries()).slice(0, 3).map((l) => [typeof l.name,
  typeof l.numColors, typeof l.numComponents, typeof l.numTypographies]);

// --- tokens of every type
const tokens = lib.tokens;
out.editable = tokens.isEditableTokens;
const set = tokens.addSet({ name: "gap", active: true });
const make = (type, name, value) => tryv(() => set.addToken({ type, name, value }));
const tk = {
  color: make("color", "gap.color", "#1971C2"),
  radius: make("borderRadius", "gap.radius", "4"),
  width: make("borderWidth", "gap.width", "2"),
  dimension: make("dimension", "gap.dimension", "16"),
  families: make("fontFamilies", "gap.families", "Roboto, sans-serif"),
  sizes: make("fontSizes", "gap.sizes", "18"),
  weights: make("fontWeights", "gap.weights", "700"),
  letter: make("letterSpacing", "gap.letter", "0.5"),
  number: make("number", "gap.number", "3"),
  opacity: make("opacity", "gap.opacity", "0.4"),
  rotation: make("rotation", "gap.rotation", "45"),
  sizing: make("sizing", "gap.sizing", "120"),
  spacing: make("spacing", "gap.spacing", "12"),
  textCase: make("textCase", "gap.case", "uppercase"),
  decoration: make("textDecoration", "gap.decoration", "underline"),
  shadow: make("shadow", "gap.shadow", [{ color: "#000000", inset: "false", offsetX: "2", offsetY: "4", spread: "0", blur: "6" }]),
  typography: make("typography", "gap.typography", { fontFamilies: "Roboto", fontSizes: "20", fontWeight: "700",
    letterSpacing: "0", lineHeight: "1.2", textCase: "none", textDecoration: "none" }),
};
out.settle6 = await settle();
const read = (x) => {
  const v = x.resolvedValue;
  const resolved = Array.isArray(v)
    ? v.map((e) => (e && typeof e === "object" ? Object.keys(e).sort().map((k) => [k, e[k]]) : e))
    : v;
  const value = x.value;
  const raw = Array.isArray(value)
    ? value.map((e) => (e && typeof e === "object" ? Object.keys(e).sort().map((k) => [k, e[k]]) : e))
    : value && typeof value === "object" ? Object.keys(value).sort().map((k) => [k, value[k]]) : value;
  return [x.type, raw, resolved];
};
out.tokens = Object.fromEntries(Object.entries(tk).map(([k, x]) => [k, typeof x === "string" ? x : read(x)]));
const sample = tk.color;
out.tokenIds = [typeof sample.id === "string", set.getTokenById(sample.id) && set.getTokenById(sample.id).name,
  typeof set.id === "string", tokens.getSetById(set.id) && tokens.getSetById(set.id).name];
out.byType = set.tokensByType.map(([type, list]) => [type, list.length]).sort();
const dupToken = sample.duplicate();
out.duplicatedToken = dupToken && dupToken.name;
dupToken.remove();
out.afterTokenRemove = set.tokens.length;
const dupSet = set.duplicate();
out.duplicatedSet = dupSet && dupSet.name;
dupSet.remove();
out.setsAfter = tokens.sets.map((s) => s.name);
const theme = tokens.addTheme({ group: "gap", name: "Light" });
theme.addSet(set);
out.theme = [typeof theme.id === "string", tokens.getThemeById(theme.id) && tokens.getThemeById(theme.id).name];
theme.removeSet(set);
out.themeSets = theme.activeSets.length;
const dupTheme = theme.duplicate();
out.duplicatedTheme = dupTheme && [dupTheme.group, dupTheme.name];
dupTheme.remove();
theme.remove();
out.themesAfter = tokens.themes.map((x) => x.name);
const target = named(penpot.createRectangle(), "token-target");
target.y = 800;
target.applyToken(tk.radius, ["borderRadiusTopLeft", "borderRadiusTopRight"]);
target.applyToken(tk.opacity);
out.settle7 = await settle();
out.applied = [target.borderRadiusTopLeft, target.borderRadiusBottomLeft, target.opacity,
  Object.keys(target.tokens || {}).sort()];

return out;
