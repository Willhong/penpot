# Server-Side Execution

In this connection, `execute_code` runs your code on the Penpot server. No browser and no plugin need to be open.
Where this section differs from the rest of the overview, this section applies.

* Open a file first: pass `fileId` (and optionally `pageId`) to `execute_code`, or call `await penpotMgmt.openFile(fileId)`.
  The session (`sessionId`, default "default") keeps that file and page open, and keeps `storage`, across calls.
  A session idle for 15 minutes or a server restart loses `storage` and the open file; open the file again then.
* Everything one call changes is saved together when the code returns. If the code throws, nothing is saved.
  The response has `result`, `log`, `commit` (saved `revn`, `changedShapeIds`, whether layout and text values were
  completed) and `engine`.
* Other people may edit the same file at the same time; their saved changes reach the session between and during calls.
  Pass `ifUnchangedSinceRevn` (a `commit.revn` you saw) to refuse the save when someone saved after that revision.
  Pass a new `requestId` with each call; a retry with the same `requestId` returns the first result instead of applying
  the change twice.
* `penpot.selection` is this session's own selection, not what the user selected in a browser. Set it to the shapes you
  work on. To find out which shapes the user means, ask for their names, or look for them in the file.
* `penpot.viewport` and `penpot.theme` read the screen of a browser tab where the same user has the file open.
  With no such tab, reading the viewport fails with `ui-only` and `theme` is "light".
  Moving the screen (setting `viewport.center` or `viewport.zoom`, `zoomReset`, `zoomToFitAll`, `zoomIntoView`) needs a
  tab with "AI follow" on; without one it fails with `ui-only`.
* `penpot.ui`, `penpot.closePlugin()`, `penpot.openViewer()` and `penpot.openPage(page, true)` fail with `ui-only`:
  there is no plugin window and no browser to navigate. `penpot.openPage(page)` changes the session's current page.
* Listeners added with `penpot.on` stay until the session ends. They hear this session's changes and the changes others
  save. They cannot send you anything; record what they see in `storage` and read it in a later call. Remove them with
  `penpot.off` when you no longer need them.
* `penpot.currentFile.export()` saves the changes the call made so far before exporting, so they are in the file:
  an error later in the same call does not undo them. It exports the `penpot` format; `zip` is no longer offered.
* A `Uint8Array` result comes back as base64 up to 1 MB. A larger one comes back as
  `{ "__type": "resource", url, size, mtype, expiresAt }`: download it within 15 minutes with the same token
  (`Authorization: Token <token>`). Return the bytes themselves, not inside an object, to get either form.
* Long work (large exports, many shapes) can run in the background: call `execute_code` with `async: true`, then
  read or cancel it with the `execution_job` tool.
* Comments (`addCommentThread`, `reply`, `resolved`, `remove`) are written at once, as in a browser: an error later
  in the same call does not undo them. Open screens show them without a reload.
* Error codes: `ui-only` (needs a browser), `forbidden`, `not-found` (also for a file you may only view),
  `validation` (invalid value), `precondition-failed`, `revn-conflict`, `vern-conflict`, `cancelled`,
  `resource-limit` (120 s or memory exceeded), `execution-error` (your code threw), `engine-error`.
