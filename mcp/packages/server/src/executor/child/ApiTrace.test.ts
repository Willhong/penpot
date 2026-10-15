import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ApiTrace } from "./ApiTrace";

// A frozen API object like the ones the sandbox hands out: tagged, with accessors and methods.
function shape(name: string): any {
    const state = { name, x: 0 };
    const proxy = Object.create(null);
    Object.defineProperties(proxy, {
        [Symbol.toStringTag]: { value: "ShapeProxy" },
        type: { value: "rectangle", enumerable: true },
        name: { get: () => state.name, set: (value) => (state.name = value), enumerable: true },
        x: { get: () => state.x, set: (value) => (state.x = value), enumerable: true },
        clone: { value: () => shape(`${state.name} copy`) },
        isSame: { value: (other: unknown) => other === proxy },
    });
    return Object.freeze(proxy);
}

function root(): any {
    const a = shape("a");
    const b = shape("b");
    const page = Object.freeze({ [Symbol.toStringTag]: "PageProxy", children: Object.freeze([a, b]) });
    return Object.freeze({
        currentPage: page,
        utils: Object.freeze({ geometry: Object.freeze({ center: (shapes: unknown[]) => shapes.length }) }),
        group: (shapes: unknown[]) => shapes.every((s) => s === a || s === b),
        later: async () => shape("later"),
        a,
    });
}

function traced(): { trace: ApiTrace; penpot: any; lines: string[] } {
    const lines: string[] = [];
    const trace = new ApiTrace((line) => lines.push(line));
    return { trace, penpot: trace.wrap(root(), "penpot"), lines };
}

function flushed(trace: ApiTrace, lines: string[]): string[] {
    trace.flush();
    const line = lines.at(-1)!;
    assert.ok(line.startsWith(ApiTrace.MARKER));
    return JSON.parse(line.slice(ApiTrace.MARKER.length));
}

describe("ApiTrace", () => {
    it("records reads, writes and calls by the object's kind", () => {
        const { trace, penpot, lines } = traced();
        const [a] = penpot.currentPage.children;
        a.x = 12;
        a.clone();
        assert.equal(a.name, "a");
        assert.deepEqual(flushed(trace, lines), [
            "PageProxy.children",
            "ShapeProxy:rectangle.clone",
            "ShapeProxy:rectangle.name",
            "ShapeProxy:rectangle.x",
            "penpot.currentPage",
        ]);
    });

    it("names plain objects by the path they were reached by", () => {
        const { trace, penpot, lines } = traced();
        assert.equal(penpot.utils.geometry.center([1, 2]), 2);
        assert.deepEqual(flushed(trace, lines), [
            "penpot.utils",
            "penpot.utils.geometry",
            "penpot.utils.geometry.center",
        ]);
    });

    it("passes the API its own objects back, also inside arrays", () => {
        const { penpot } = traced();
        const [a, b] = penpot.currentPage.children;
        assert.equal(penpot.group([a, b]), true);
        assert.equal(a.isSame(penpot.a), true);
        assert.equal(penpot.a, a);
    });

    it("reads frozen properties without breaking the proxy invariants", () => {
        const { penpot } = traced();
        const page = penpot.currentPage;
        assert.equal(page.children.length, 2);
        assert.deepEqual(Object.keys(penpot.a), ["type", "name", "x"]);
        assert.equal(JSON.stringify(penpot.a), JSON.stringify({ type: "rectangle", name: "a", x: 0 }));
        assert.equal(Object.prototype.toString.call(page), "[object PageProxy]");
    });

    it("keeps the refusals of frozen objects, with their own message", () => {
        const { penpot } = traced();
        assert.throws(
            () => {
                penpot.currentPage.missing = 1;
            },
            { name: "TypeError", message: /Cannot add property missing, object is not extensible/ }
        );
    });

    it("wraps what promises resolve to", async () => {
        const { trace, penpot, lines } = traced();
        const later = await penpot.later();
        assert.equal(later.name, "later");
        assert.ok(flushed(trace, lines).includes("ShapeProxy:rectangle.name"));
    });

    it("writes nothing for an execution that touched no member, and starts over after a flush", () => {
        const { trace, penpot, lines } = traced();
        trace.flush();
        assert.equal(lines.length, 0);
        void penpot.a;
        trace.flush();
        void penpot.utils;
        assert.deepEqual(flushed(trace, lines), ["penpot.utils"]);
    });
});
