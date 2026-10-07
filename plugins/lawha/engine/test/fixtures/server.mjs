// A small app for the login and readiness tests: /private needs a session (cookie or header),
// /spa draws its content well after the load event, as a client-rendered app does.
import { createServer } from "node:http";

const page = (title, body = "") => `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title></head><body><main><h1>${title}</h1>${body}</main></body></html>`;

let shiftLoads = 0;
const server = createServer((req, res) => {
  const signedIn = /(?:^|;\s*)session=ok(?:;|$)/.test(req.headers.cookie ?? "") || req.headers["x-token"] === "t";
  if (req.url === "/private" && !signedIn) {
    res.writeHead(302, { location: "/login?next=/private" }).end();
  } else if (req.url === "/private") {
    res.writeHead(200, { "content-type": "text/html" }).end(page("Private"));
  } else if (req.url?.startsWith("/login")) {
    res.writeHead(200, { "content-type": "text/html" }).end(page("Sign in"));
  } else if (req.url === "/spa") {
    const late = `<script>setTimeout(() => { const i = document.createElement("img"); i.id = "late"; i.width = 40; i.height = 40; i.src = "data:image/gif;base64,R0lGODlhAQABAAAAACw="; document.querySelector("main").append(i); }, 8000);</script>`;
    res.writeHead(200, { "content-type": "text/html" }).end(page("App", late));
  } else if (req.url === "/shift") {
    // Shifts on the first load only: a cold cache, a slow font. One unlucky load is not the page.
    const late = shiftLoads++ === 0 ? `<script>setTimeout(() => document.querySelector("h1").before(Object.assign(document.createElement("div"), { style: "height:300px;background:#eef" })), 300);</script>` : "";
    res.writeHead(200, { "content-type": "text/html" }).end(page("Shift", `<p style="min-height:500px;background:#f6f6f6">Some text that is pushed down.</p>${late}`));
  } else {
    res.writeHead(404).end();
  }
});
server.listen(0, "127.0.0.1", () => process.stdout.write(`${server.address().port}\n`));
