import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, openSync, closeSync, readdirSync, readFileSync, renameSync, unlinkSync, writeSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
/**
 * How lawha tells the other Nexika plugins what it checked.
 *
 * The record of each check is kept in lawha's own folder (~/.claude/nexika/lawha/checks/<project>/,
 * guarded by haris so no agent can write a fake pass there). The shared status file
 * ~/.claude/nexika/status/lawha.json (schema nexika.lawha/1) only points at the latest record per
 * project, the same contract as itqan's proofs: mizan and itqan trust a pointer only when it leads
 * into lawha's folder.
 */
export const RECORD_SCHEMA = "nexika.lawha.check/1";
export const STATUS_SCHEMA = "nexika.lawha/1";
const KEEP = 20;
export function lawhaHome() {
    return resolve(process.env.LAWHA_HOME || join(homedir(), ".claude", "nexika", "lawha"));
}
export function statusHome() {
    return resolve(process.env.NEXIKA_STATUS_HOME || join(homedir(), ".claude", "nexika", "status"));
}
function git(cwd, ...args) {
    try {
        return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 10_000 }).trim();
    }
    catch {
        return "";
    }
}
/** The project a check belongs to: the git top level of the working folder, else the folder. */
export function projectRoot(cwd) {
    return resolve(git(cwd, "rev-parse", "--show-toplevel") || cwd);
}
/** Owner-only folders, as every Nexika plugin creates them. */
function ensureDir(folder) {
    const missing = [];
    let f = folder;
    while (!existsSync(f)) {
        missing.push(f);
        f = dirname(f);
    }
    for (const one of missing.reverse()) {
        mkdirSync(one, { mode: 0o700 });
        chmodSync(one, 0o700);
    }
}
/** Atomic, owner-only JSON write. */
function writeJsonSafe(path, data) {
    ensureDir(dirname(path));
    const tmp = join(dirname(path), `.${path.split("/").pop()}.${process.pid}.tmp`);
    const fd = openSync(tmp, "w", 0o600);
    try {
        writeSync(fd, JSON.stringify(data, null, 1));
    }
    finally {
        closeSync(fd);
    }
    renameSync(tmp, path);
}
export function record(cwd, data) {
    const project = projectRoot(cwd);
    const rec = {
        schema: RECORD_SCHEMA,
        created: new Date().toISOString().slice(0, 19),
        project,
        branch: git(project, "rev-parse", "--abbrev-ref", "HEAD"),
        commit: git(project, "rev-parse", "--short", "HEAD"),
        dirty: git(project, "status", "--porcelain") !== "",
        ...data,
        problems: data.problems.filter((p) => p.severity !== "info").slice(0, 15).map((p) => ({ severity: p.severity, check: p.check, message: p.message.slice(0, 300), where: p.where })),
    };
    const folder = join(lawhaHome(), "checks", createHash("sha1").update(project).digest("hex").slice(0, 16));
    const stamp = rec.created.replace(/[-:]/g, "").replace("T", "-");
    writeJsonSafe(join(folder, `${stamp}.json`), rec);
    const latest = join(folder, "latest.json");
    writeJsonSafe(latest, rec);
    const old = readdirSync(folder).filter((n) => /^2\d{7}-\d{6}\.json$/.test(n)).sort();
    for (const name of old.slice(0, Math.max(0, old.length - KEEP)))
        unlinkSync(join(folder, name));
    publish(project, latest);
    return latest;
}
/** status/lawha.json: the latest check per project (only files that still exist are kept). */
export function publish(project, latest) {
    const path = join(statusHome(), "lawha.json");
    let checks = {};
    try {
        const current = JSON.parse(readFileSync(path, "utf8"));
        for (const [k, v] of Object.entries(current.checks ?? {}))
            if (typeof v === "string" && existsSync(v))
                checks[k] = v;
    }
    catch {
        checks = {};
    }
    checks[project] = latest;
    writeJsonSafe(path, { schema: STATUS_SCHEMA, updated: Math.floor(Date.now() / 1000), checks });
}
