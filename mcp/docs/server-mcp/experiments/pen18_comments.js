// PEN-18 scenario: comment threads. Creates threads on the page and on a
// board, replies, edits a comment, resolves, moves and removes threads, and
// queries them with filters. Returns what the getters read back (no ids or
// dates). Runs unchanged in a browser workspace and in the server-side
// executor (dual_run.py).

const board = penpot.createBoard();
board.name = "Board";
board.x = 100;
board.y = 100;
board.resize(300, 200);
await penpot.waitForLayoutUpdate(10000);
const page = penpot.currentPage;

const onPage = await page.addCommentThread("A thread on the page", { x: 20, y: 30 });
const onBoard = await page.addCommentThread("A thread on the board", { x: 150, y: 160 });
const doomed = await page.addCommentThread("A thread to remove", { x: 600, y: 40 });
const reply = await onBoard.reply("A reply");
await onBoard.reply("Another reply");
reply.content = "An edited reply";
onPage.resolved = true;
onBoard.position = { x: 180, y: 170 };
await doomed.remove();

const readThread = async (thread) => ({
  seq: thread.seqNumber,
  board: thread.board ? thread.board.name : null,
  owner: thread.owner ? thread.owner.name : null,
  position: thread.position,
  resolved: thread.resolved,
  comments: (await thread.findComments()).map((c) => [c.user.name, c.content]),
});
const all = await page.findCommentThreads({ onlyYours: false, showResolved: true });
const open = await page.findCommentThreads({ onlyYours: false, showResolved: false });
const mine = await page.findCommentThreads({ onlyYours: true, showResolved: true });

return {
  threads: await Promise.all(all.sort((a, b) => a.seqNumber - b.seqNumber).map(readThread)),
  counts: { all: all.length, open: open.length, mine: mine.length },
};
