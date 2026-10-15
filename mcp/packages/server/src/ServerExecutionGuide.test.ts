import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ApiDocs } from "./ApiDocs";
import { ConfigurationLoader } from "./ConfigurationLoader";
import { ServerExecutionGuide } from "./ServerExecutionGuide";

describe("ServerExecutionGuide", () => {
    const loader = new ConfigurationLoader(process.cwd());

    it("replaces the plugin precondition and adds the server section before the closing line", () => {
        const overview = ServerExecutionGuide.overview(
            loader.getInitialInstructions(),
            loader.getServerExecutionInstructions()
        );
        assert.ok(!overview.includes(ServerExecutionGuide.PLUGIN_PRECONDITION));
        assert.ok(overview.includes("# Server-Side Execution"));
        assert.ok(overview.indexOf("# Server-Side Execution") < overview.lastIndexOf("\n--\n"));
        assert.ok(overview.trimEnd().endsWith("need not use a tool to read it again."));
    });

    it("notes only members whose server meaning differs", () => {
        assert.match(ServerExecutionGuide.memberNote("Penpot", "viewport")!, /ui-only/);
        assert.match(ServerExecutionGuide.memberNote("Viewport", "zoomToFitAll")!, /AI follow/);
        assert.equal(ServerExecutionGuide.memberNote("Penpot", "createRectangle"), null);
        assert.equal(ServerExecutionGuide.typeNotes("Shape"), null);
        assert.match(ServerExecutionGuide.typeNotes("Viewport")!, /^- center: /);
    });

    it("notes members that exist in the API docs", () => {
        const docs = new ApiDocs();
        for (const type of ["Penpot", "Context", "Viewport"]) {
            const apiType = docs.getType(type);
            assert.ok(apiType, type);
            for (const line of ServerExecutionGuide.typeNotes(type)!.split("\n")) {
                const member = line.slice(2, line.indexOf(":"));
                assert.ok(apiType.getMember(member), `${type}.${member}`);
            }
        }
    });
});
