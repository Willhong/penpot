// Minimal write: one rectangle with position, size and color, as in PEN-3.
const rect = penpot.createRectangle();
rect.name = "server-mcp-rect";
rect.x = 120;
rect.y = 80;
rect.resize(200, 120);
rect.fills = [{ fillColor: "#E8590C", fillOpacity: 1 }];
return { id: rect.id, x: rect.x, y: rect.y, width: rect.width, height: rect.height };
