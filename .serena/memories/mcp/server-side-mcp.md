# Server-side MCP (browserless editing) — preparation material

Fork-specific work (Plane PEN-23 → PEN-22). Goal: an MCP that edits and exports Penpot files with no user browser open, covering the whole Plugin API (716 members) and all MCP tools.

- Docs index: `mcp/docs/server-mcp/README.md`. Contract (`01-feature-contract.md`), research (`02-browser-dependency-research.md`), runtime contract (`03-runtime-contract.md`), generated scope (`feature-inventory.md`).
- Scope check: `python3 -I mcp/docs/server-mcp/tools/gen_inventory.py --check` fails on any Plugin API member or MCP tool not mapped to an owning ticket. Rerun after changing `plugins/libs/plugin-types/index.d.ts` or `mcp/packages/server/src/tools/`.
- Isolated test stack: `scripts/mcp-verify-env up|wait|seed|status|logs|down|destroy --yes` (own compose project, DB, bucket, Valkey; loopback ports 3549/3550/4501/1180). Fixtures (4 profiles: owner/editor/viewer/outsider, API + MCP tokens) in `.mcp-verify/fixtures.json`. Never point it at production data. Details: `mcp/docs/server-mcp/verification-env.md`.
- Key facts:
  - backend `update-file` applies and validates changes with cljc on the JVM.
  - The browser computes derived values (layout, text size, bool, token values) before saving; with `render-wasm/v1` (default flag) that is the Rust module.
  - The exporter already runs render-wasm headless under Node (`exporter/src/app/wasm.cljs`).
  - Stale `revn` is accepted; a `revn` ahead of the server is a `revn-conflict`; there is no request dedup.
  - The WebSocket drops this connection's own `session-id`, so each server session needs its own UUID.
- Executor (E4 proven 2026-10-15): the frontend's own store, workspace events and `app.plugins.api` run under plain Node with render-wasm booted by `_init_headless` (`frontend/src/app/executor/`, shadow build `:executor`). Results equal a wasm-mode browser exactly (`experiments/e4_headless_compute.py`). `app.common.render-wasm.wasm/headless?` marks this mode; render-wasm skips tile/render-state work when there is no render state.
- The browser's default renderer is `:svg` (profile prop `:renderer`, `render-switch` flag), not wasm; compare against a profile switched to wasm.
- MCP tokens (`iss urn:penpot:mcp-token`) are rejected by `app.http.access-token/decode-token` on purpose (test `mcp-tokens-cannot-be-used-as-access-tokens`).
- Gotchas:
  - The exporter needs `PENPOT_INTERNAL_URI` when the public port differs from the container port.
  - The frontend and exporter watchers race on `rustup default` in a fresh container.
  - Transit fragments cannot be spliced because of key caching.
  - The executor must set `:session-id` in state (the browser's `app.main/initialize` does) or `update-file` fails validation.
  - `p/let` awaits promise bindings: subscribe-then-emit through a helper, not a binding.
  - `$TMPDIR` differs inside and outside the agent sandbox; keep experiment output in `.mcp-verify/`.
