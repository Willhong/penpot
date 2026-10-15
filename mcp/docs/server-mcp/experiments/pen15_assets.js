// PEN-15 scenario: library colors and typographies, and design tokens. Creates,
// edits, applies and removes colors and typographies, replaces a color across
// shapes; creates token sets, themes and tokens of several types with aliases
// and math, applies them to shapes, changes values so they propagate, and
// toggles sets and themes. Returns what the getters read back. Runs unchanged
// in a browser workspace and in the server-side executor (dual_run.py); every
// shape is named.

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
const lib = penpot.library.local;

// --- colors
const brand = lib.createColor();
brand.name = "Brand";
brand.path = "Palette";
brand.color = "#5F3DC4";
brand.opacity = 0.9;
const accent = lib.createColor();
accent.name = "Accent";
accent.color = "#F08C00";
const fade = lib.createColor();
fade.name = "Fade";
fade.gradient = {
  type: "linear", startX: 0, startY: 0, endX: 1, endY: 1, width: 1,
  stops: [{ color: "#FFFFFF", opacity: 1, offset: 0 }, { color: "#000000", opacity: 1, offset: 1 }],
};
const a = named(penpot.createRectangle(), "a");
a.fills = [brand.asFill()];
a.strokes = [accent.asStroke()];
const b = named(penpot.createRectangle(), "b");
b.x = 150;
b.fills = [accent.asFill()];
const c = named(penpot.createEllipse(), "c");
c.x = 300;
c.fills = [fade.asFill()];
const used = penpot.shapesColors([a, b, c]);
const colorsBefore = used.map((x) => [x.color, x.opacity, x.refId ? "ref" : null, x.shapeInfo ? x.shapeInfo.length : null]);
const accentUse = used.find((x) => x.color && x.color.toUpperCase() === "#F08C00");
penpot.replaceColor([a, b], accentUse, { color: "#2F9E44", opacity: 1 });
brand.color = "#1971C2";
const toRemove = lib.createColor();
toRemove.name = "Temp";
toRemove.color = "#000000";
toRemove.remove();
await settle("colors");

// --- typographies
const title = lib.createTypography();
title.name = "Title";
title.path = "Text styles";
title.fontSize = "28";
title.fontWeight = "700";
title.lineHeight = "1.3";
title.letterSpacing = "0.5";
title.textTransform = "uppercase";
const roboto = penpot.fonts.findByName("Roboto");
const body = lib.createTypography();
body.name = "Body";
if (roboto) {
  body.setFont(roboto, roboto.variants.find((v) => v.fontWeight === "400" && v.fontStyle === "normal"));
}
body.fontSize = "16";
const heading = named(penpot.createText("Heading styled by a library typography"), "heading");
heading.y = 200;
const paragraph = named(penpot.createText("Body text with a styled range"), "paragraph");
paragraph.y = 260;
await settle("texts");
title.applyToText(heading);
body.applyToTextRange(paragraph.getRange(0, 4));
await settle("typographies");

// --- tokens
const tokens = lib.tokens;
const core = tokens.addSet({ name: "core", active: true });
const dark = tokens.addSet({ name: "dark", active: false });
const t = {};
t.primary = core.addToken({ type: "color", name: "color.primary", value: "#E03131" });
t.alias = core.addToken({ type: "color", name: "color.action", value: "{color.primary}" });
t.space = core.addToken({ type: "spacing", name: "space.base", value: "8" });
t.spaceTwice = core.addToken({ type: "spacing", name: "space.double", value: "{space.base} * 2" });
t.radius = core.addToken({ type: "borderRadius", name: "radius.card", value: "12px" });
t.size = core.addToken({ type: "sizing", name: "size.box", value: "120" });
t.opacity = core.addToken({ type: "opacity", name: "opacity.muted", value: "0.5" });
t.stroke = core.addToken({ type: "borderWidth", name: "stroke.thin", value: "2" });
t.fontSize = core.addToken({ type: "fontSizes", name: "font.size.lg", value: "22" });
t.darkPrimary = dark.addToken({ type: "color", name: "color.primary", value: "#212529" });
const theme = tokens.addTheme({ group: "mode", name: "Dark" });
theme.addSet(dark);
await settle("tokensCreated");

const box = named(penpot.createRectangle(), "box");
box.x = 0;
box.y = 400;
const board = named(penpot.createBoard(), "padded");
board.x = 200;
board.y = 400;
board.addFlexLayout();
const inner = named(penpot.createRectangle(), "inner");
board.flex.appendChild(inner);
const label = named(penpot.createText("Token sized text"), "label");
label.y = 600;
await settle("tokenTargets");
t.alias.applyToShapes([box], ["fill"]);
t.radius.applyToShapes([box]);
t.size.applyToShapes([box], ["width", "height"]);
t.opacity.applyToShapes([box]);
t.stroke.applyToShapes([box], ["strokeWidth"]);
t.spaceTwice.applyToShapes([board], ["paddingLeft", "paddingTop"]);
t.fontSize.applyToShapes([label]);
await settle("tokensApplied");

const snapshot = () => ({
  box: { fill: box.fills[0] && box.fills[0].fillColor, radius: box.borderRadius, w: box.width, h: box.height,
         opacity: box.opacity, stroke: box.strokes[0] ? box.strokes[0].strokeWidth : null,
         tokens: Object.keys(box.tokens || {}).sort() },
  padded: { left: board.flex.leftPadding, top: board.flex.topPadding, w: board.width, h: board.height,
            innerX: inner.x, innerY: inner.y },
  label: { fontSize: label.fontSize, w: label.width, h: label.height },
});
const applied = snapshot();

// propagation: a changed value reaches the shapes that use it
t.primary.value = "#1C7ED6";
t.space.value = "10";
t.size.value = "140";
t.fontSize.value = "30";
await settle("valuesChanged");
const propagated = snapshot();

// a theme that activates the dark set overrides color.primary
theme.toggleActive();
await settle("themeOn");
const themed = { resolved: t.alias.resolvedValueString, sets: tokens.sets.map((s) => [s.name, s.active]), ...snapshot() };
theme.toggleActive();
dark.toggleActive();
dark.toggleActive();
await settle("themeOff");

const readToken = (token) => ({ name: token.name, type: token.type, value: token.value, resolved: token.resolvedValueString });
return {
  waits,
  colorsBefore,
  colors: lib.colors.map((x) => ({ name: x.name, path: x.path, color: x.color, opacity: x.opacity, gradient: !!x.gradient }))
    .sort((p, q) => p.name.localeCompare(q.name)),
  shapesAfterReplace: [a, b, c].map((s) => [s.name, s.fills[0] && s.fills[0].fillColor, s.strokes[0] && s.strokes[0].strokeColor]),
  typographies: lib.typographies.map((x) => ({ name: x.name, path: x.path, fontFamily: x.fontFamily, fontSize: x.fontSize,
    fontWeight: x.fontWeight, lineHeight: x.lineHeight, letterSpacing: x.letterSpacing, textTransform: x.textTransform }))
    .sort((p, q) => p.name.localeCompare(q.name)),
  heading: { fontSize: heading.fontSize, fontWeight: heading.fontWeight, transform: heading.textTransform, w: heading.width, h: heading.height },
  paragraphRange: { family: paragraph.getRange(0, 4).fontFamily, rest: paragraph.getRange(5, 9).fontFamily, w: paragraph.width },
  tokens: Object.fromEntries(Object.entries(t).map(([k, token]) => [k, readToken(token)])),
  sets: tokens.sets.map((s) => ({ name: s.name, active: s.active, count: s.tokens.length })),
  themes: tokens.themes.map((x) => ({ group: x.group, name: x.name, active: x.active, sets: x.activeSets.map((s) => s.name), externalId: x.externalId })),
  applied,
  propagated,
  themed,
};
