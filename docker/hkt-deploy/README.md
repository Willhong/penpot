# design.hktlabs.com deployment

Fork-specific build and deploy files for the server-side MCP (PEN-21).
The guide, the procedure, the rollback and the verification record are in
[`mcp/docs/server-mcp/07-deployment.md`](../../mcp/docs/server-mcp/07-deployment.md).

| File | Purpose |
|---|---|
| `build.sh` | Builds the frontend, backend, exporter and MCP+executor images of one commit on nucbox and pushes them to Harbor |
| `Dockerfile.mcp-executor` | Adds the frontend `:executor` build, its node_modules and render-wasm to the release MCP image |
| `values.yaml` | Helm values layered over the release's base values; image tags come from `--set-string` |
| `rollback-rehearsal.sh` | Runs install → upgrade → rollback in a throwaway namespace |
