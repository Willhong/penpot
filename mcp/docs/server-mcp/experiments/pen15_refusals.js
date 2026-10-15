// PEN-15 refusals: invalid colors, typographies and tokens must be refused or
// ignored the same way in a browser workspace and in the server-side executor
// (dual_run.py): alias cycles, missing references, invalid values. Returns each
// attempt's outcome and what is left.

const lib = penpot.library.local;
const color = lib.createColor();
color.name = "Base";
color.color = "#FF0000";
const typo = lib.createTypography();
typo.name = "Type";
const tokens = lib.tokens;
const core = tokens.addSet({ name: "core", active: true });
const ok = core.addToken({ type: "color", name: "color.ok", value: "#00FF00" });
const box = penpot.createRectangle();
box.name = "box";
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
  colorBadHex: attempt(() => {
    color.color = "red-ish";
  }),
  colorOpacityHigh: attempt(() => {
    color.opacity = 3;
  }),
  colorNameEmpty: attempt(() => {
    color.name = "";
  }),
  typoSizeText: attempt(() => {
    typo.fontSize = "big";
  }),
  typoWeightBad: attempt(() => {
    typo.fontWeight = "heaviest";
  }),
  tokenTypeBad: attempt(() => core.addToken({ type: "smell", name: "x.y", value: "1" })),
  tokenNameBad: attempt(() => core.addToken({ type: "color", name: "{bad}", value: "#000000" })),
  tokenNameDuplicate: attempt(() => core.addToken({ type: "color", name: "color.ok", value: "#000000" })),
  tokenValueBad: attempt(() => core.addToken({ type: "color", name: "color.bad", value: "not a color" })),
  tokenMissingRef: attempt(() => core.addToken({ type: "color", name: "color.missing", value: "{color.nowhere}" })),
  tokenSelfRef: attempt(() => core.addToken({ type: "color", name: "color.self", value: "{color.self}" })),
  tokenCycle: attempt(() => {
    core.addToken({ type: "spacing", name: "space.a", value: "4" });
    const b = core.addToken({ type: "spacing", name: "space.b", value: "{space.a}" });
    const a = core.tokens.find((t) => t.name === "space.a");
    a.value = "{space.b}";
    return [a.value, b.value];
  }),
  tokenMathBad: attempt(() => core.addToken({ type: "spacing", name: "space.math", value: "4 * * 2" })),
  tokenValueChangeBad: attempt(() => {
    ok.value = "#zzzzzz";
  }),
  applyToNothing: attempt(() => ok.applyToShapes([])),
  applyWrongProperty: attempt(() => ok.applyToShapes([box], ["fontFamilies"])),
  setNameEmpty: attempt(() => tokens.addSet({ name: "" })),
  themeNoName: attempt(() => tokens.addTheme({ group: "g", name: "" })),
  replaceColorBad: attempt(() => penpot.replaceColor([box], { color: "nope" }, { color: "#000000" })),
};
await penpot.waitForLayoutUpdate(10000);

return {
  outcomes,
  color: { name: color.name, color: color.color, opacity: color.opacity },
  typo: { fontSize: typo.fontSize, fontWeight: typo.fontWeight },
  tokens: core.tokens.map((t) => [t.name, t.value, t.resolvedValueString]).sort(),
  sets: tokens.sets.map((s) => s.name),
  box: { fill: box.fills[0] && box.fills[0].fillColor, tokens: Object.keys(box.tokens || {}) },
};
