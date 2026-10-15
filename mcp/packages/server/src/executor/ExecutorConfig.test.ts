import { after, describe, it } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ExecutorConfig } from "./ExecutorConfig";

const dir = mkdtempSync(join(tmpdir(), "executor-config-"));
after(() => rmSync(dir, { recursive: true, force: true }));

function env(extra: Record<string, string>): Record<string, string> {
    return {
        PENPOT_MCP_EXECUTOR_BUNDLE: join(dir, "executor.js"),
        PENPOT_MCP_EXECUTOR_PUBLIC_URI: "http://backend",
        ...extra,
    };
}

describe("ExecutorConfig version", () => {
    it("is the one the frontend build next to the wasm directory declares", () => {
        mkdirSync(join(dir, "build", "js"), { recursive: true });
        writeFileSync(
            join(dir, "build", "index.html"),
            '<script>penpotVersion = "2.9.0-12-gabc";\npenpotVersionTag = "x";</script>'
        );
        const config = new ExecutorConfig(env({ PENPOT_MCP_EXECUTOR_WASM_DIR: join(dir, "build", "js") }));
        assert.equal(config.version, "2.9.0-12-gabc");
    });

    it("is PENPOT_VERSION when set", () => {
        const config = new ExecutorConfig(
            env({ PENPOT_MCP_EXECUTOR_WASM_DIR: join(dir, "build", "js"), PENPOT_VERSION: "3.0.0" })
        );
        assert.equal(config.version, "3.0.0");
    });

    it("is empty without either", () => {
        const config = new ExecutorConfig(env({ PENPOT_MCP_EXECUTOR_WASM_DIR: join(dir, "nowhere", "js") }));
        assert.equal(config.version, "");
    });
});
