// PEN-9 gap scenario (3/3): comment members no earlier scenario ran on the
// server: a comment's date, removing a reply, removing a thread from its
// page. Runs unchanged in a browser workspace and in the server-side
// executor (pen9_gaps.py).

const board = penpot.createBoard();
board.name = "commented";
board.resize(200, 120);
const thread = await penpot.currentPage.addCommentThread("Gap thread", { x: 20, y: 20 });
const reply = await thread.reply("Gap reply");
const comments = await thread.findComments();
const out = {
  dates: comments.map((c) => c.date instanceof Date && !Number.isNaN(c.date.getTime())),
  contents: comments.map((c) => c.content),
};
await reply.remove();
out.afterReplyRemoved = (await thread.findComments()).map((c) => c.content);
await penpot.currentPage.removeCommentThread(thread);
out.threadsAfter = (await penpot.currentPage.findCommentThreads()).length;
return out;
