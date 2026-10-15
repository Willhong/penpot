// PEN-5 refusals: invalid values and combinations. Each attempt is caught,
// so the scenario returns what the API answered; the shapes must keep their
// previous values. Runs unchanged in a browser workspace and on the server.

const rect = penpot.createRectangle();
rect.name = "target";
rect.resize(100, 50);
rect.fills = [{ fillColor: "#228be6", fillOpacity: 1 }];

const attempts = {
  opacityTooHigh: () => { rect.opacity = 2; },
  negativeSize: () => { rect.resize(-10, 20); },
  badBlendMode: () => { rect.blendMode = "sideways"; },
  badFillColor: () => { rect.fills = [{ fillColor: "red-ish", fillOpacity: 1 }]; },
  badFillOpacity: () => { rect.fills = [{ fillColor: "#ffffff", fillOpacity: 3 }]; },
  badStrokeStyle: () => { rect.strokes = [{ strokeColor: "#000000", strokeStyle: "wavy", strokeWidth: 1 }]; },
  badShadowStyle: () => { rect.shadows = [{ style: "glow", offsetX: 1, offsetY: 1, blur: 1, spread: 0, color: { color: "#000000", opacity: 1 } }]; },
  badExportType: () => { rect.exports = [{ type: "gif", scale: 1 }]; },
  badRadius: () => { rect.borderRadius = "round"; },
  badName: () => { rect.name = 42; },
  badPluginDataValue: () => { rect.setPluginData("k", 5); },
  clipOnRectangle: () => { rect.clipContent = false; },
  removedShape: () => { const e = penpot.createEllipse(); e.name = "gone"; e.remove(); e.x = 10; },
};

const answers = {};
for (const [name, attempt] of Object.entries(attempts)) {
  try {
    attempt();
    answers[name] = "accepted";
  } catch (e) {
    answers[name] = String(e && e.message ? e.message : e);
  }
}

return {
  answers,
  after: {
    opacity: rect.opacity,
    width: rect.width,
    blendMode: rect.blendMode,
    fills: rect.fills,
    strokes: rect.strokes,
    shadows: rect.shadows,
    exports: rect.exports,
    borderRadius: rect.borderRadius,
    name: rect.name,
    pluginData: rect.getPluginDataKeys(),
  },
};
