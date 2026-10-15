import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ExecutorError } from "./ExecutorError";
import { MemoryResultBackend, ResultStore } from "./ResultStore";

const envelope = (bytes: Buffer) => ({ __type: "base64", data: bytes.toString("base64") });

describe("ResultStore", () => {
    it("keeps small results inline and hands large ones out by URL, to their owner only", async () => {
        const store = new ResultStore(new MemoryResultBackend(), 10);
        const small = envelope(Buffer.from("tiny"));
        assert.equal(await store.deliver(small, "alice", "http://mcp"), small);
        assert.deepEqual(await store.deliver({ answer: 42 }, "alice", "http://mcp"), { answer: 42 });

        const pdf = Buffer.from("%PDF-1.4 a document larger than ten bytes");
        const handed = (await store.deliver(envelope(pdf), "alice", "http://mcp/")) as any;
        assert.equal(handed.__type, "resource");
        assert.equal(handed.size, pdf.length);
        assert.equal(handed.mtype, "application/pdf");
        assert.match(handed.url, /^http:\/\/mcp\/results\/[0-9a-f-]{36}$/);
        const id = handed.url.split("/").pop();
        assert.deepEqual(await store.get("alice", id), pdf);
        assert.equal(await store.get("bob", id), null);
    });

    it("forgets results once they expire", async () => {
        const store = new ResultStore(new MemoryResultBackend(), 1, 20);
        const handed = (await store.deliver(envelope(Buffer.from("PK zip bytes")), "alice", "http://mcp")) as any;
        await new Promise((resolve) => setTimeout(resolve, 40));
        assert.equal(await store.get("alice", handed.url.split("/").pop()), null);
    });

    it("refuses results over the size limit", async () => {
        const store = new ResultStore(new MemoryResultBackend());
        await assert.rejects(
            store.store(Buffer.alloc(ResultStore.MAX_BYTES + 1), "alice", "http://mcp"),
            (error: unknown) => error instanceof ExecutorError && error.code === "resource-limit"
        );
    });

    it("sniffs the formats Penpot exports", () => {
        assert.equal(ResultStore.sniff(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a])), "image/png");
        assert.equal(ResultStore.sniff(Buffer.from([0xff, 0xd8, 0xff])), "image/jpeg");
        assert.equal(ResultStore.sniff(Buffer.from("RIFF0000WEBPVP8 ")), "image/webp");
        assert.equal(ResultStore.sniff(Buffer.from("<svg xmlns='http://www.w3.org/2000/svg'/>")), "image/svg+xml");
        assert.equal(ResultStore.sniff(Buffer.from("PK\u0003\u0004")), "application/zip");
        assert.equal(ResultStore.sniff(Buffer.from("plain")), "application/octet-stream");
    });
});
