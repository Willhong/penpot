// PEN-12 refusals: invalid text values must be refused or ignored the same way
// in a browser workspace and in the server-side executor (dual_run.py).
// Returns each attempt's outcome and the text left behind.

const t = penpot.createText("Refusal sample text");
t.name = "t";
try {
  await penpot.waitForLayoutUpdate(5000);
} catch (error) {
  // the comparison covers the same wait on both sides
}

const attempt = (fn) => {
  try {
    const value = fn();
    return { ok: true, value: value === undefined ? null : value };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
};

const outcomes = {
  createEmpty: attempt(() => penpot.createText("")),
  createNumber: attempt(() => penpot.createText(42)),
  fontSizeText: attempt(() => {
    t.fontSize = "big";
  }),
  fontSizeNegative: attempt(() => {
    t.fontSize = "-4";
  }),
  fontWeightBad: attempt(() => {
    t.fontWeight = "heavy";
  }),
  lineHeightBad: attempt(() => {
    t.lineHeight = "tall";
  }),
  alignBad: attempt(() => {
    t.align = "middle";
  }),
  growTypeBad: attempt(() => {
    t.growType = "auto";
  }),
  directionBad: attempt(() => {
    t.direction = "up";
  }),
  rangeOutOfBounds: attempt(() => t.getRange(5, 500).characters),
  rangeReversed: attempt(() => t.getRange(10, 2).characters),
  rangeFontSizeBad: attempt(() => {
    t.getRange(0, 4).fontSize = "huge";
  }),
  fontFamilyUnknown: attempt(() => {
    t.fontFamily = "No Such Font Family";
  }),
  findUnknownFont: attempt(() => penpot.fonts.findByName("No Such Font Family")),
  charactersEmpty: attempt(() => {
    t.characters = "";
  }),
};

return {
  outcomes,
  text: {
    characters: t.characters,
    fontSize: t.fontSize,
    fontWeight: t.fontWeight,
    fontFamily: t.fontFamily,
    lineHeight: t.lineHeight,
    align: t.align,
    growType: t.growType,
    direction: t.direction,
    width: t.width,
    height: t.height,
  },
};
