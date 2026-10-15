// PEN-12 scenario: texts in Latin, Korean, emoji, right-to-left and several
// paragraphs; every text style property, range styles, the three grow types,
// wrapping, and fonts chosen from the catalog (a bundled one and Google ones).
// Waits for the text layout, then returns what the getters read back. Runs
// unchanged in a browser workspace and in the server-side executor
// (dual_run.py); every shape is named.

const board = penpot.createBoard();
board.name = "board";
board.resize(1000, 900);
board.fills = [{ fillColor: "#ffffff", fillOpacity: 1 }];

const text = (name, characters, x, y) => {
  const shape = penpot.createText(characters);
  shape.name = name;
  board.appendChild(shape);
  shape.x = x;
  shape.y = y;
  return shape;
};

// let the texts get their first measure before sizing them
const settle = async () => {
  try {
    await penpot.waitForLayoutUpdate(5000);
  } catch (error) {
    return String(error.message || error);
  }
  return "ok";
};

const latin = text("latin", "Hello Penpot server text", 20, 20);
const korean = text("korean", "안녕하세요. 서버에서 한글 텍스트의 줄바꿈과 크기를 계산합니다.", 20, 100);
const emoji = text("emoji", "Emoji 😀🎉👍 and 한글 mixed", 20, 260);
const paragraphs = text("paragraphs", "First paragraph\nSecond paragraph, a longer one that wraps\n\nFourth after an empty one", 20, 330);
const mixed = text("mixed", "Bold red big italic underline normal", 20, 520);
const rtl = text("rtl", "שלום עולם مرحبا بالعالم", 520, 20);
const fixed = text("fixed", "A fixed box whose text wraps and is centred vertically inside its height", 520, 120);
const google = text("google", "Roboto and Work Sans 폰트", 520, 380);
const waits = [await settle()];

// every style property of a whole text
latin.fontSize = "24";
latin.fontWeight = "700";
latin.lineHeight = "1.4";
latin.letterSpacing = "2";
latin.textDecoration = "underline";
latin.textTransform = "uppercase";
latin.align = "center";
latin.fills = [{ fillColor: "#1971c2", fillOpacity: 1 }];

// auto-height at a set width: the height follows the wrapped lines
korean.growType = "fixed";
korean.resize(220, 40);
korean.growType = "auto-height";
korean.fontSize = "18";
korean.lineHeight = "1.6";

emoji.fontSize = "28";
paragraphs.growType = "fixed";
paragraphs.resize(240, 60);
paragraphs.growType = "auto-height";
paragraphs.align = "justify";

// range styles
mixed.fontSize = "16";
mixed.getRange(0, 4).fontWeight = "700";
mixed.getRange(5, 8).fills = [{ fillColor: "#e03131", fillOpacity: 1 }];
mixed.getRange(9, 12).fontSize = "30";
mixed.getRange(13, 19).fontStyle = "italic";
mixed.getRange(20, 29).textDecoration = "underline";
mixed.getRange(9, 12).letterSpacing = "4";

rtl.direction = "rtl";
rtl.align = "right";
rtl.fontSize = "20";

fixed.growType = "fixed";
fixed.resize(200, 220);
fixed.verticalAlign = "center";
fixed.align = "center";
fixed.fontSize = "18";

// fonts from the catalog: a Google font for the whole text, another for a range
const roboto = penpot.fonts.findByName("Roboto");
const workSans = penpot.fonts.findByName("Work Sans");
if (roboto) {
  roboto.applyToText(google, roboto.variants.find((v) => v.fontWeight === "500" && v.fontStyle === "normal"));
}
if (workSans) {
  workSans.applyToRange(google.getRange(11, 20));
}
google.fontSize = "26";
waits.push(await settle());

const read = (shape) => ({
  name: shape.name,
  characters: shape.characters,
  growType: shape.growType,
  x: shape.x,
  y: shape.y,
  width: shape.width,
  height: shape.height,
  fontId: shape.fontId,
  fontFamily: shape.fontFamily,
  fontVariantId: shape.fontVariantId,
  fontSize: shape.fontSize,
  fontWeight: shape.fontWeight,
  fontStyle: shape.fontStyle,
  lineHeight: shape.lineHeight,
  letterSpacing: shape.letterSpacing,
  textTransform: shape.textTransform,
  textDecoration: shape.textDecoration,
  direction: shape.direction,
  align: shape.align,
  verticalAlign: shape.verticalAlign,
});

const ranges = (shape, cuts) =>
  cuts.map(([start, end]) => {
    const range = shape.getRange(start, end);
    return {
      start,
      end,
      characters: range.characters,
      fontFamily: range.fontFamily,
      fontSize: range.fontSize,
      fontWeight: range.fontWeight,
      fontStyle: range.fontStyle,
      textDecoration: range.textDecoration,
      letterSpacing: range.letterSpacing,
      fills: range.fills,
    };
  });

return {
  waits,
  fontsFound: { roboto: !!roboto, workSans: !!workSans, catalog: penpot.fonts.all.length > 100 },
  texts: [latin, korean, emoji, paragraphs, mixed, rtl, fixed, google].map(read),
  ranges: {
    mixed: ranges(mixed, [[0, 4], [5, 8], [9, 12], [13, 19], [20, 29], [0, 36]]),
    google: ranges(google, [[0, 6], [11, 20]]),
  },
};
