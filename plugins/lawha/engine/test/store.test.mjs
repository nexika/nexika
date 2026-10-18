// #394: lawha's own files survive damage and concurrent writers. No browser needed.
import { strict as assert } from "node:assert";
import { execFileSync, spawn } from "node:child_process";
import { chmodSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const CLI = join(ROOT, "dist", "cli.js");
const tmp = () => mkdtempSync(join(tmpdir(), "lawha-test-"));
const homes = () => ({ LAWHA_HOME: tmp(), NEXIKA_STATUS_HOME: tmp() });
const lawha = (env, cwd, ...args) => JSON.parse(execFileSync(process.execPath, [CLI, ...args], { encoding: "utf8", timeout: 60_000, env: { ...process.env, ...env }, cwd }));
const broken = (folder, name) => readdirSync(folder).filter((f) => f.startsWith(`${name}.broken-`));
const leftovers = (folder) => readdirSync(folder).filter((f) => f.endsWith(".tmp"));

/** A finished blind comparison, without rendering: reveal only reads the key. */
function abRun() {
  const out = tmp();
  mkdirSync(join(out, ".key"));
  writeFileSync(join(out, ".key", "key.json"), JSON.stringify({ schema: "nexika.lawha.ab/1", a: { url: "x", label: "current" }, b: { url: "y", label: "candidate" }, left: "a", widths: [390], created: "now" }));
  return out;
}
const pick = (env, note = "n") => lawha(env, undefined, "ab", "reveal", abRun(), "--pick", "left", "--by", "user", "--note", note);

test("taste.json holding an object is treated as empty, kept aside, and the pick is recorded", () => {
  const env = homes();
  writeFileSync(join(env.LAWHA_HOME, "taste.json"), "{}");
  assert.equal(pick(env).recorded, true);
  const taste = JSON.parse(readFileSync(join(env.LAWHA_HOME, "taste.json"), "utf8"));
  assert.equal(taste.length, 1);
  assert.equal(broken(env.LAWHA_HOME, "taste.json").length, 1);
});

test("a truncated taste.json is moved aside, never silently overwritten", () => {
  const env = homes();
  const damaged = '[{"at":"2026-01-01","project":"/p","winner":"a","loser":"b","note":"kept"},{"at":';
  writeFileSync(join(env.LAWHA_HOME, "taste.json"), damaged);
  pick(env, "fresh");
  const aside = broken(env.LAWHA_HOME, "taste.json");
  assert.equal(aside.length, 1);
  assert.equal(readFileSync(join(env.LAWHA_HOME, aside[0]), "utf8"), damaged, "the old picks can be recovered");
  assert.deepEqual(lawha(env, undefined, "ab", "taste").map((t) => t.note), ["fresh"]);
});

test("taste entries that are not objects are skipped, good ones kept; non-UTF-8 counts as damaged", () => {
  const env = homes();
  writeFileSync(join(env.LAWHA_HOME, "taste.json"), JSON.stringify([null, 3, "x", { at: "t", project: "/p", winner: "a", loser: "b", note: "old" }]));
  assert.deepEqual(lawha(env, undefined, "ab", "taste").map((t) => t.note), ["old"]);
  pick(env, "new");
  assert.deepEqual(lawha(env, undefined, "ab", "taste").map((t) => t.note), ["old", "new"]);
  assert.equal(broken(env.LAWHA_HOME, "taste.json").length, 0, "a readable file is not moved");

  const bad = homes();
  writeFileSync(join(bad.LAWHA_HOME, "taste.json"), Buffer.concat([Buffer.from('[{"note":"'), Buffer.from([0xff, 0xfe]), Buffer.from('"}]')]));
  pick(bad);
  assert.equal(broken(bad.LAWHA_HOME, "taste.json").length, 1);
});

test("taste.json is replaced atomically, owner-only, with no temp file left", () => {
  const env = homes();
  pick(env);
  const path = join(env.LAWHA_HOME, "taste.json");
  const before = statSync(path).ino;
  pick(env);
  assert.notEqual(statSync(path).ino, before, "written to a temp file and renamed over");
  assert.equal(statSync(path).mode & 0o777, 0o600);
  assert.deepEqual(leftovers(env.LAWHA_HOME), []);
});

const direction = {
  id: "a", name: "A", mood: "calm", signature: "a line", motif: "underline", motion: "calm", layout: "editorial",
  fonts: { display: { family: "Fraunces", weights: [600] }, text: { family: "Source Sans 3", weights: [400] } },
  scale: { base: 17, ratio: 1.25 }, radius: 6, spacing: 4,
  palette: {
    light: { background: "#FAF7F2", surface: "#FFFFFF", text: "#1B2330", muted: "#566070", primary: "#1F3A5F", primaryText: "#FFFFFF", accent: "#E5A93B", border: "#C9BFAF" },
    dark: { background: "#12161D", surface: "#1A2029", text: "#EEF1F5", muted: "#A7B0BE", primary: "#8DB3E2", primaryText: "#0E1A2B", accent: "#E5A93B", border: "#3A4554" },
  },
};

test("a damaged history.json is moved aside; design.json is replaced atomically and keeps its mode", () => {
  const env = homes();
  const app = tmp();
  writeFileSync(join(app, "package.json"), "{}");
  writeFileSync(join(app, "directions.json"), JSON.stringify([direction]));
  writeFileSync(join(env.LAWHA_HOME, "history.json"), '[{"id":"x"');
  mkdirSync(join(app, ".lawha"));
  const design = join(app, ".lawha", "design.json");
  writeFileSync(design, "{}");
  chmodSync(design, 0o640);
  const before = statSync(design).ino;
  const chosen = lawha(env, app, "direct", "choose", "directions.json", "a");
  assert.equal(chosen.history, 1);
  assert.equal(broken(env.LAWHA_HOME, "history.json").length, 1);
  assert.equal(readFileSync(join(env.LAWHA_HOME, broken(env.LAWHA_HOME, "history.json")[0]), "utf8"), '[{"id":"x"');
  assert.notEqual(statSync(design).ino, before);
  assert.equal(statSync(design).mode & 0o777, 0o640, "the person's file keeps its mode");
  assert.equal(statSync(join(env.LAWHA_HOME, "history.json")).mode & 0o777, 0o600);
  assert.deepEqual(leftovers(join(app, ".lawha")), []);
});

test("the Figma call log: bad entries are skipped, a damaged log is moved aside", async () => {
  const env = homes();
  process.env.LAWHA_HOME = env.LAWHA_HOME;
  process.env.FIGMA_TOKEN = "test";
  const log = join(env.LAWHA_HOME, "figma-calls.json");
  const now = Date.now();
  writeFileSync(log, JSON.stringify([null, 7, { at: now, endpoint: "/files/:key", tier: 1, status: 200 }]));
  const figma = await import(pathToFileURL(join(ROOT, "dist", "figma.js")).href);
  assert.equal(figma.budget().tier1Last30Days, 1, "one bad entry must not hide the good ones");
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ versions: [{ id: "1", created_at: "t" }] }), { status: 200 });
  try {
    writeFileSync(log, '[{"at":1');
    await figma.latestVersion("abcdefghijkl");
    assert.equal(broken(env.LAWHA_HOME, "figma-calls.json").length, 1);
    assert.equal(JSON.parse(readFileSync(log, "utf8")).length, 1);
    assert.equal(statSync(log).mode & 0o777, 0o600);
  } finally {
    globalThis.fetch = realFetch;
  }
});

/** Run `publish` in a separate process, `n` times for different projects. */
function publisher(env, tag, n, latest) {
  const code = `const { publish } = await import(${JSON.stringify(pathToFileURL(join(ROOT, "dist", "record.js")).href)});
for (let i = 0; i < ${n}; i++) publish("/project/${tag}-" + i, ${JSON.stringify(latest)});`;
  return new Promise((done, fail) => {
    const p = spawn(process.execPath, ["--input-type=module", "-e", code], { env: { ...process.env, ...env }, stdio: "inherit" });
    p.on("exit", (c) => (c === 0 ? done() : fail(new Error(`publisher exited ${c}`))));
  });
}

test("two checks finishing at once both stay in status/lawha.json", async () => {
  const env = homes();
  const latest = join(env.LAWHA_HOME, "latest.json");
  writeFileSync(latest, "{}");
  await Promise.all(Array.from({ length: 6 }, (_, k) => publisher(env, `p${k}`, 40, latest)));
  const status = JSON.parse(readFileSync(join(env.NEXIKA_STATUS_HOME, "lawha.json"), "utf8"));
  assert.equal(Object.keys(status.checks).length, 6 * 40);
  assert.deepEqual(readdirSync(env.NEXIKA_STATUS_HOME).filter((f) => f !== "lawha.json"), [], "no lock or temp file left");
});

test("a stale lock is broken at once; a held lock delays the write but never stops it", async () => {
  const env = homes();
  const latest = join(env.LAWHA_HOME, "latest.json");
  writeFileSync(latest, "{}");
  const lock = join(env.NEXIKA_STATUS_HOME, ".lawha.json.wlock");
  writeFileSync(lock, "");
  const old = (Date.now() - 120_000) / 1000;
  utimesSync(lock, old, old);
  let t = Date.now();
  await publisher(env, "stale", 1, latest);
  assert.ok(Date.now() - t < 1500, "a stale lock does not make the write wait");
  assert.equal(existsSync(lock), false);

  writeFileSync(lock, "");
  t = Date.now();
  await publisher(env, "held", 1, latest);
  assert.ok(Date.now() - t < 10_000);
  const status = JSON.parse(readFileSync(join(env.NEXIKA_STATUS_HOME, "lawha.json"), "utf8"));
  assert.ok(status.checks["/project/held-0"], "written anyway");
  assert.equal(existsSync(lock), true, "someone else's lock is not removed");
});

test("a checks map of the wrong type is replaced, not spread into the file", async () => {
  const env = homes();
  const latest = join(env.LAWHA_HOME, "latest.json");
  writeFileSync(latest, "{}");
  writeFileSync(join(env.NEXIKA_STATUS_HOME, "lawha.json"), JSON.stringify({ schema: "nexika.lawha/1", checks: [latest, latest] }));
  await publisher(env, "x", 1, latest);
  const status = JSON.parse(readFileSync(join(env.NEXIKA_STATUS_HOME, "lawha.json"), "utf8"));
  assert.deepEqual(Object.keys(status.checks), ["/project/x-0"]);
});

/** One publish in a child process, killed after `limit` ms: a hang shows as a signal, never as a stuck test run. */
function publishOnce(env, project, latest, limit = 15_000) {
  const code = `const { publish } = await import(${JSON.stringify(pathToFileURL(join(ROOT, "dist", "record.js")).href)});
publish(${JSON.stringify(project)}, ${JSON.stringify(latest)});`;
  const t = Date.now();
  return new Promise((done) => {
    const p = spawn(process.execPath, ["--input-type=module", "-e", code], { env: { ...process.env, ...env }, stdio: "ignore", timeout: limit });
    p.on("exit", (code, signal) => done({ code, signal, ms: Date.now() - t }));
  });
}
const ageOld = (path) => { const old = (Date.now() - 120_000) / 1000; utimesSync(path, old, old); };

test("a stale lock that cannot be removed (folder not writable) never hangs the write", async () => {
  const env = homes();
  const latest = join(env.LAWHA_HOME, "latest.json");
  writeFileSync(latest, "{}");
  const lock = join(env.NEXIKA_STATUS_HOME, ".lawha.json.wlock");
  writeFileSync(lock, "");
  ageOld(lock);
  chmodSync(env.NEXIKA_STATUS_HOME, 0o500);
  try {
    const r = await publishOnce(env, "/project/ro", latest);
    assert.equal(r.signal, null, `publish hung (${r.ms} ms)`);
    assert.ok(r.ms < 10_000, `${r.ms} ms`);
  } finally {
    chmodSync(env.NEXIKA_STATUS_HOME, 0o700);
  }
});

test("a lock path that is a folder never hangs the write; it waits, then writes without the lock", async () => {
  const env = homes();
  const latest = join(env.LAWHA_HOME, "latest.json");
  writeFileSync(latest, "{}");
  const lock = join(env.NEXIKA_STATUS_HOME, ".lawha.json.wlock");
  mkdirSync(lock);
  ageOld(lock);
  const r = await publishOnce(env, "/project/dir", latest);
  assert.equal(r.signal, null, `publish hung (${r.ms} ms)`);
  assert.equal(r.code, 0);
  const status = JSON.parse(readFileSync(join(env.NEXIKA_STATUS_HOME, "lawha.json"), "utf8"));
  assert.ok(status.checks["/project/dir"]);
});

test("the lock is released only while it is still ours; a stale one is taken over without leftovers", async () => {
  const { withLock } = await import(pathToFileURL(join(ROOT, "dist", "util.js")).href);
  const folder = tmp();
  const lock = join(folder, "x.wlock");
  withLock(lock, () => {
    // Someone else took the lock over meanwhile (as if ours had looked stale to them).
    rmSync(lock);
    writeFileSync(lock, "someone else");
  });
  assert.equal(readFileSync(lock, "utf8"), "someone else", "another writer's lock is not removed");
  ageOld(lock);
  let ran = false;
  withLock(lock, () => { ran = true; });
  assert.ok(ran);
  assert.deepEqual(readdirSync(folder), [], "the stale lock and our own are both gone");
});

test("the person's project files: mode kept despite the umask, symlinks followed, read-only refused", () => {
  const env = homes();
  const app = tmp();
  writeFileSync(join(app, "package.json"), "{}");
  writeFileSync(join(app, "directions.json"), JSON.stringify([direction]));
  mkdirSync(join(app, ".lawha"));
  const design = join(app, ".lawha", "design.json");
  const old = process.umask(0o022);
  try {
    writeFileSync(design, "{}");
    chmodSync(design, 0o664);
    lawha(env, app, "direct", "choose", "directions.json", "a");
    assert.equal(statSync(design).mode & 0o777, 0o664, "group-writable stays group-writable");

    rmSync(design);
    const real = join(app, "real-design.json");
    writeFileSync(real, "{}");
    symlinkSync(real, design);
    lawha(env, app, "direct", "choose", "directions.json", "a");
    assert.ok(lstatSync(design).isSymbolicLink(), "the link stays a link");
    assert.equal(JSON.parse(readFileSync(real, "utf8")).direction.id, "a");

    rmSync(design);
    writeFileSync(design, "{}");
    chmodSync(design, 0o444);
    assert.throws(() => lawha(env, app, "direct", "choose", "directions.json", "a"), /EACCES|permission/i);
    assert.equal(readFileSync(design, "utf8"), "{}", "a read-only file is not overwritten");
  } finally {
    process.umask(old);
  }
});

test("picks saved at the same moment are all kept", async () => {
  const env = homes();
  const runs = Array.from({ length: 6 }, () => abRun());
  const code = (out) => `const { reveal } = await import(${JSON.stringify(pathToFileURL(join(ROOT, "dist", "ab.js")).href)});
for (let i = 0; i < 15; i++) reveal(${JSON.stringify(out)}, "left", "user", "n" + i, ${JSON.stringify(tmpdir())});`;
  await Promise.all(runs.map((out) => new Promise((done, fail) => {
    const p = spawn(process.execPath, ["--input-type=module", "-e", code(out)], { env: { ...process.env, ...env }, stdio: "inherit", timeout: 60_000 });
    p.on("exit", (c) => (c === 0 ? done() : fail(new Error(`reveal exited ${c}`))));
  })));
  assert.equal(JSON.parse(readFileSync(join(env.LAWHA_HOME, "taste.json"), "utf8")).length, 90);
  assert.equal(broken(env.LAWHA_HOME, "taste.json").length, 0, "a file mid-write is never set aside");
  assert.deepEqual(readdirSync(env.LAWHA_HOME).filter((f) => f !== "taste.json"), []);
});
