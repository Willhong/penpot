/**
 * Integration test of the server-side executor's isolation (PEN-10), against the mcp-verify stack.
 *
 * Drives an {@link ExecutorPool} directly (no MCP transport) with the seeded users' MCP tokens and checks:
 *  - `storage` is kept within a session and not shared between users or between sessions of one user;
 *  - concurrent executions of two users each save to their own file only;
 *  - user code cannot reach the process (`process`, `require`, `fetch`, modules, constructor escapes);
 *  - an endless loop and a memory blow-up end with `resource-limit`, save nothing, and the session
 *    starts afresh on the next call;
 *  - a restarted pool has no state of the previous one.
 *
 * Needs the stack (scripts/mcp-verify-env), the executor bundle (frontend/scripts/build-executor) and
 * `pnpm run build`. Run inside the main container, from packages/server:
 *   pnpm run test:integration:executor
 *
 * Prints a JSON report; exit status 1 when a check fails.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ExecutorConfig } from "../src/executor/ExecutorConfig";
import { ExecutorError } from "../src/executor/ExecutorError";
import { ExecutorPool } from "../src/executor/ExecutorPool";

const ROOT = resolve(import.meta.dirname, "..", "..", "..", "..");
const fixtures = JSON.parse(readFileSync(resolve(ROOT, ".mcp-verify/fixtures.json"), "utf-8"));
const token = (role: string) => fixtures.profiles[role].tokens.mcp as string;
const apiToken = (role: string) => fixtures.profiles[role].tokens.api as string;
const backend = process.env.MCPV_BACKEND_URI ?? "http://localhost:3450";

const env = {
    ...process.env,
    PENPOT_MCP_EXECUTOR: "server",
    PENPOT_MCP_EXECUTOR_CHILD: resolve(import.meta.dirname, "..", "dist", "executor-child.js"),
    PENPOT_MCP_EXECUTOR_BUNDLE:
        process.env.PENPOT_MCP_EXECUTOR_BUNDLE ?? resolve(ROOT, "frontend/target/executor/executor.js"),
    PENPOT_MCP_EXECUTOR_WASM_DIR:
        process.env.PENPOT_MCP_EXECUTOR_WASM_DIR ?? resolve(ROOT, "frontend/resources/public/js"),
    PENPOT_MCP_EXECUTOR_PUBLIC_URI: backend,
    PENPOT_MCP_SHARED_KEY: process.env.PENPOT_MCP_SHARED_KEY ?? "super-secret-mcp-key",
    PENPOT_MCP_EXECUTOR_TIMEOUT_S: "15",
};

async function rpc(method: string, params: object, role = "editor"): Promise<any> {
    const response = await fetch(`${backend}/api/main/methods/${method}`, {
        method: "POST",
        headers: {
            "content-type": "application/json",
            accept: "application/json",
            authorization: `Token ${apiToken(role)}`,
        },
        body: JSON.stringify(params),
    });
    if (!response.ok) {
        throw new Error(`${method}: ${response.status} ${await response.text()}`);
    }
    return response.json();
}

async function createFile(name: string, role: string): Promise<string> {
    const file = await rpc("create-file", { name, projectId: fixtures.project.id }, role);
    return file.id;
}

async function fileState(fileId: string): Promise<{ revn: number; names: string[] }> {
    const file = await rpc("get-file", { id: fileId });
    const page = file.data.pagesIndex[file.data.pages[0]];
    return {
        revn: file.revn,
        names: Object.values(page.objects)
            .map((shape: any) => shape.name)
            .sort(),
    };
}

async function outcome(
    run: () => Promise<any>
): Promise<{ ok: boolean; value?: unknown; code?: string; message?: string }> {
    try {
        const result = await run();
        return { ok: true, value: result.result };
    } catch (error) {
        return error instanceof ExecutorError
            ? { ok: false, code: error.code, message: error.message.slice(0, 200) }
            : { ok: false, code: "unexpected", message: String(error).slice(0, 200) };
    }
}

const ESCAPES: Record<string, string> = {
    process: "return typeof process;",
    require: "return typeof require;",
    fetch: "return typeof fetch;",
    globalProcess: "return typeof globalThis.process;",
    dynamicImport: "const fs = await import('node:fs'); return typeof fs.readFileSync;",
    functionConstructor: "return typeof Function('return this')().process;",
    arrowConstructor: "return typeof (() => {}).constructor('return this')().process;",
    asyncConstructor: "return typeof (await (async () => {}).constructor('return this')()).process;",
    penpotConstructor: "return typeof penpot.constructor.constructor('return this')().process;",
    storageConstructor: "return typeof storage.constructor.constructor('return this')().process;",
    consoleConstructor: "return typeof console.log.constructor('return this')().process;",
    utilsConstructor: "return typeof penpotUtils.constructor.constructor('return this')().process;",
    shapeConstructor:
        "const s = penpot.createRectangle(); const r = typeof s.constructor.constructor('return this')().process; s.remove(); return r;",
};

async function main(): Promise<void> {
    const report: Record<string, any> = {};
    const failed: string[] = [];
    const check = (name: string, ok: boolean, detail: unknown) => {
        report[name] = { ok, detail };
        if (!ok) failed.push(name);
    };

    const ownerFile = await createFile("pen10-owner", "owner");
    const editorFile = await createFile("pen10-editor", "editor");
    let pool = new ExecutorPool(new ExecutorConfig(env));

    // storage per session
    await pool.execute(token("editor"), "a", {
        code: "storage.who = 'editor-a'; return storage.who;",
        fileId: editorFile,
    });
    await pool.execute(token("editor"), "b", {
        code: "storage.who = 'editor-b'; return storage.who;",
        fileId: editorFile,
    });
    await pool.execute(token("owner"), "a", {
        code: "storage.who = 'owner-a'; return storage.who;",
        fileId: ownerFile,
    });
    const reads = {
        editorA: (await pool.execute(token("editor"), "a", { code: "return storage.who;" })).result,
        editorB: (await pool.execute(token("editor"), "b", { code: "return storage.who;" })).result,
        ownerA: (await pool.execute(token("owner"), "a", { code: "return storage.who;" })).result,
        // a global variable does not outlive its execution
        globalLeak: (await pool.execute(token("editor"), "a", { code: "globalThis.leak = 1; return 0;" })).result,
        globalAfter: (await pool.execute(token("editor"), "a", { code: "return typeof globalThis.leak;" })).result,
    };
    check(
        "storageIsolation",
        reads.editorA === "editor-a" &&
            reads.editorB === "editor-b" &&
            reads.ownerA === "owner-a" &&
            reads.globalAfter === "undefined",
        reads
    );

    // concurrent users, each in their own file
    const rect = (name: string) => `const r = penpot.createRectangle(); r.name = '${name}'; return r.id;`;
    const before = { owner: await fileState(ownerFile), editor: await fileState(editorFile) };
    const [ownerRun, editorRun] = await Promise.all([
        pool.execute(token("owner"), "a", { code: rect("owner-concurrent"), fileId: ownerFile }),
        pool.execute(token("editor"), "a", { code: rect("editor-concurrent"), fileId: editorFile }),
    ]);
    const after = { owner: await fileState(ownerFile), editor: await fileState(editorFile) };
    check(
        "concurrentUsers",
        after.owner.names.includes("owner-concurrent") &&
            !after.owner.names.includes("editor-concurrent") &&
            after.editor.names.includes("editor-concurrent") &&
            !after.editor.names.includes("owner-concurrent") &&
            after.owner.revn === before.owner.revn + 1 &&
            after.editor.revn === before.editor.revn + 1,
        { ownerCommit: ownerRun.commit, editorCommit: editorRun.commit, after }
    );

    // sandbox escapes
    const escapes: Record<string, unknown> = {};
    for (const [name, code] of Object.entries(ESCAPES)) {
        escapes[name] = await outcome(() => pool.execute(token("editor"), "escape", { code, fileId: editorFile }));
    }
    // a snippet escapes when it runs and finds what it looked for (anything but "undefined")
    const escaped = Object.entries(escapes).filter(
        ([, result]: [string, any]) => result.ok && result.value !== "undefined"
    );
    check("sandboxEscapes", escaped.length === 0, escapes);

    // endless loop: resource-limit, nothing saved, the session restarts
    const loopBefore = await fileState(editorFile);
    const loop = await outcome(() =>
        pool.execute(token("editor"), "loop", {
            code: "penpot.createRectangle().name = 'loop-rect'; while (true) {}",
            fileId: editorFile,
        })
    );
    const loopAfter = await fileState(editorFile);
    const loopNext = await outcome(() => pool.execute(token("editor"), "loop", { code: "return typeof storage.x;" }));
    check(
        "endlessLoop",
        loop.code === "resource-limit" &&
            loopAfter.revn === loopBefore.revn &&
            !loopAfter.names.includes("loop-rect") &&
            loopNext.ok,
        { loop, loopNext, revn: [loopBefore.revn, loopAfter.revn] }
    );

    // derived values that do not finish within the settle bound: resource-limit, nothing saved (the text
    // waits for a font variant this session has not downloaded yet, which outlasts the 1 ms bound)
    const settleBefore = await fileState(editorFile);
    const layoutCode =
        "const b = penpot.createBoard(); b.name = 'settle-board'; const f = b.addFlexLayout(); f.wrap = 'wrap';" +
        " const t = penpot.createText('Settle'); t.fontWeight = '700'; t.fontStyle = 'italic'; f.appendChild(t);" +
        " for (let i = 0; i < 200; i++) { const r = penpot.createRectangle(); r.name = 'settle-rect'; f.appendChild(r); }" +
        " return 1;";
    const unsettled = await outcome(() =>
        pool.execute(token("editor"), "settle", { code: layoutCode, fileId: editorFile, settleTimeoutMs: 1 })
    );
    const settleAfter = await fileState(editorFile);
    const settled = await outcome(() => pool.execute(token("editor"), "settle", { code: layoutCode }));
    check(
        "unsettledDerivedValues",
        unsettled.code === "resource-limit" &&
            (unsettled.message ?? "").includes("did not finish") &&
            settleAfter.revn === settleBefore.revn &&
            !settleAfter.names.includes("settle-board") &&
            settled.ok,
        { unsettled, settled, revn: [settleBefore.revn, settleAfter.revn] }
    );

    // memory blow-up
    const memBefore = await fileState(editorFile);
    const memory = await outcome(() =>
        pool.execute(token("editor"), "memory", {
            code: "penpot.createRectangle().name = 'mem-rect'; const a = []; while (true) { a.push(new Array(1e6).fill(Math.random())); }",
            fileId: editorFile,
        })
    );
    const memAfter = await fileState(editorFile);
    check(
        "memoryBlowUp",
        memory.code === "resource-limit" && memAfter.revn === memBefore.revn && !memAfter.names.includes("mem-rect"),
        { memory, revn: [memBefore.revn, memAfter.revn] }
    );

    // restart: no state survives
    await pool.close();
    pool = new ExecutorPool(new ExecutorConfig(env));
    const restarted = await outcome(() =>
        pool.execute(token("editor"), "a", {
            code: "return [typeof storage.who, penpot.currentFile ? 'file' : 'no-file'];",
        })
    );
    check(
        "restart",
        restarted.ok && JSON.stringify(restarted.value) === JSON.stringify(["undefined", "no-file"]),
        restarted
    );
    await pool.close();

    console.log(JSON.stringify({ failed, report }, null, 2));
    process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
