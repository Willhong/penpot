// PEN-16 refusals: unsafe or invalid images and SVG must be refused the same way
// in a browser workspace and in the server-side executor (dual_run.py): URLs
// to internal addresses, other schemes, disguised and oversized data,
// external entities, entity expansion, scripts, malformed markup.

const attempt = async (fn) => {
  try {
    const value = await fn();
    return { ok: true, value: value === undefined ? null : value };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error).slice(0, 200) };
  }
};
const kinds = (shape) => shape && { type: shape.type, children: (shape.children || []).map((c) => c.type) };

const outcomes = {
  urlLoopback: await attempt(async () => (await penpot.uploadMediaUrl("lo", "http://127.0.0.1:6060/api/main/methods/get-profile")).width),
  urlBackendHost: await attempt(async () => (await penpot.uploadMediaUrl("be", "http://localhost:3450/")).width),
  urlMetadata: await attempt(async () => (await penpot.uploadMediaUrl("md", "http://169.254.169.254/latest/meta-data/")).width),
  urlPrivate: await attempt(async () => (await penpot.uploadMediaUrl("pv", "http://10.0.0.1/x.png")).width),
  urlFile: await attempt(async () => (await penpot.uploadMediaUrl("f", "file:///etc/passwd")).width),
  urlFtp: await attempt(async () => (await penpot.uploadMediaUrl("ftp", "ftp://example.com/x.png")).width),
  urlNotImage: await attempt(async () => (await penpot.uploadMediaUrl("html", "https://www.w3.org/")).width),
  dataDisguised: await attempt(async () => (await penpot.uploadMediaData("fake", new TextEncoder().encode("<html>not an image</html>"), "image/png")).width),
  dataOversized: await attempt(async () => (await penpot.uploadMediaData("big", new Uint8Array(40 * 1024 * 1024), "image/png")).width),
  svgExternalEntity: await attempt(() => kinds(penpot.createShapeFromSvg('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><text y="20">&xxe;</text></svg>'))),
  svgEntityExpansion: await attempt(() => kinds(penpot.createShapeFromSvg('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;"><!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">]><svg xmlns="http://www.w3.org/2000/svg"><text>&d;&d;&d;&d;&d;</text></svg>'))),
  svgScript: await attempt(() => kinds(penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><script>fetch("http://169.254.169.254/")</script><rect width="10" height="10" onload="alert(1)"/><a href="javascript:alert(1)"><rect x="20" width="10" height="10"/></a></svg>'))),
  svgForeignObject: await attempt(() => kinds(penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><foreignObject width="50" height="50"><div xmlns="http://www.w3.org/1999/xhtml">html</div></foreignObject></svg>'))),
  svgMalformed: await attempt(() => kinds(penpot.createShapeFromSvg("<svg><rect></svg"))),
  svgNotSvg: await attempt(() => kinds(penpot.createShapeFromSvg("hello"))),
  svgInternalImage: await attempt(async () => kinds(await penpot.createShapeFromSvgWithImages('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><image width="20" height="20" href="http://169.254.169.254/x.png"/><image x="20" width="20" height="20" href="file:///etc/passwd"/><rect y="15" width="40" height="5"/></svg>'))),
};
await penpot.waitForLayoutUpdate(10000);
return { outcomes, shapes: penpot.currentPage.findShapes().map((s) => s.type).sort() };
