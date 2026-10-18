import { randomBytes } from "node:crypto";
import { accessSync, closeSync, constants, existsSync, fchmodSync, linkSync, lstatSync, mkdirSync, openSync, readFileSync, readlinkSync, realpathSync, renameSync, statSync, unlinkSync, writeSync } from "node:fs";
import { availableParallelism } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
export const DEFAULT_WIDTHS = [360, 390, 768, 1024, 1280, 1536];
export const PHONE_MAX = 767;
/** Variants rendered at once in `check`: one per CPU, up to 8 (bench/speed.mjs: 5x faster at 8 on 12 CPUs). */
export const DEFAULT_CONCURRENCY = Math.max(1, Math.min(8, availableParallelism()));
/** Minimal flag parser: --name value, --name=value, --flag (boolean); a repeated flag collects its values. */
export function parseArgs(argv, booleans = [], repeated = []) {
    const out = { _: [] };
    for (let i = 0; i < argv.length; i++) {
        const arg = argv[i];
        if (!arg.startsWith("--")) {
            out._.push(arg);
            continue;
        }
        const cut = arg.indexOf("=");
        const name = cut < 0 ? arg.slice(2) : arg.slice(2, cut);
        const inline = cut < 0 ? undefined : arg.slice(cut + 1);
        const value = inline !== undefined ? inline : booleans.includes(name) ? true : (argv[++i] ?? "");
        if (repeated.includes(name))
            out[name] = [...(out[name] ?? []), String(value)];
        else
            out[name] = value;
    }
    return out;
}
export function list(value, fallback) {
    if (typeof value !== "string" || !value.trim())
        return fallback;
    return value.split(",").map((v) => v.trim()).filter(Boolean);
}
export function writeJson(path, data) {
    mkdirSync(dirname(path), { recursive: true });
    writeAtomic(path, JSON.stringify(data, null, 2) + "\n");
}
/** The file a path finally names: a symlink is followed, even to a file that does not exist yet. */
function realTarget(path) {
    for (let p = path, hops = 0; hops < 40; hops++) {
        try {
            if (!lstatSync(p).isSymbolicLink())
                return p;
        }
        catch {
            return p;
        }
        try {
            return realpathSync(p);
        }
        catch {
            p = resolve(dirname(p), readlinkSync(p));
        }
    }
    return path;
}
/**
 * Replace a file in one step: write a temp file beside it, then rename it over the target, so a
 * reader never sees half a file and a crash never leaves one. `mode` forces the file's mode (0o600
 * for lawha's own files). Without it, as a plain write would: an existing file keeps its mode, a file
 * we may not write is refused (EACCES), a symlink stays a link and its target is replaced.
 */
export function writeAtomic(path, text, mode) {
    const target = realTarget(path);
    let keep = mode;
    if (keep === undefined && existsSync(target)) {
        accessSync(target, constants.W_OK);
        keep = statSync(target).mode & 0o777;
    }
    const tmp = join(dirname(target), `.${basename(target)}.${process.pid}.${randomBytes(4).toString("hex")}.tmp`);
    const fd = openSync(tmp, "wx", keep ?? 0o666);
    try {
        try {
            if (keep !== undefined)
                fchmodSync(fd, keep); // the umask must not narrow a kept mode
            writeSync(fd, text);
        }
        finally {
            closeSync(fd);
        }
        renameSync(tmp, target);
    }
    catch (err) {
        try {
            unlinkSync(tmp);
        }
        catch { /* already gone */ }
        throw err;
    }
}
/**
 * A JSON list kept in a file. Entries that fail `keep` are skipped. `damaged` is true when the file
 * exists but is not a readable JSON list (cut short, not UTF-8, an object): the caller then moves it
 * aside with `setAside` before writing a fresh one, so nothing the person had is lost.
 */
export function readList(path, keep) {
    let raw;
    try {
        raw = readFileSync(path);
    }
    catch {
        return { items: [], damaged: existsSync(path) };
    }
    try {
        const data = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(raw));
        if (!Array.isArray(data))
            return { items: [], damaged: true };
        return { items: data.filter(keep), damaged: false };
    }
    catch {
        return { items: [], damaged: true };
    }
}
export const isObject = (v) => typeof v === "object" && v !== null && !Array.isArray(v);
/** Move a damaged file to <name>.broken-<time> so it can be recovered by hand. */
export function setAside(path) {
    try {
        renameSync(path, `${path}.broken-${stamp()}-${randomBytes(2).toString("hex")}`);
    }
    catch { /* gone already */ }
}
/** Write a JSON list back; a damaged file found when reading is moved aside first. */
export function writeList(path, items, damaged, compact = false) {
    mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    if (damaged)
        setAside(path);
    writeAtomic(path, compact ? JSON.stringify(items) : JSON.stringify(items, null, 1), 0o600);
}
/**
 * Read, change and write back one of lawha's JSON lists under its lock, so two writers at once both
 * keep their entry. Returns the list as written.
 */
export function updateList(path, keep, change, compact = false) {
    mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    return withLock(join(dirname(path), `.${basename(path)}.wlock`), () => {
        const { items, damaged } = readList(path, keep);
        const out = change(items);
        writeList(path, out, damaged, compact);
        return out;
    });
}
const SLEEP = new Int32Array(new SharedArrayBuffer(4));
/**
 * Remove a lock left from a crash. Renaming first means only one of several writers that saw the
 * same stale lock takes it over; one that renamed a fresh lock by mistake puts it back.
 * True when the lock is gone and creating it can be tried again at once.
 */
function takeStale(lockPath, staleMs) {
    try {
        const st = statSync(lockPath);
        if (!st.isFile() || Date.now() - st.mtimeMs <= staleMs)
            return false;
        const aside = `${lockPath}.stale-${process.pid}-${randomBytes(4).toString("hex")}`;
        renameSync(lockPath, aside);
        try {
            if (statSync(aside).ino !== st.ino) {
                try {
                    linkSync(aside, lockPath);
                }
                catch { /* a newer lock is already there */ }
            }
        }
        finally {
            try {
                unlinkSync(aside);
            }
            catch { /* gone */ }
        }
        return true;
    }
    catch (err) {
        return err.code === "ENOENT"; // already removed by someone else
    }
}
/**
 * Run `work` holding an exclusive lock file (created with O_EXCL). Waits up to `waitMs`; a lock older
 * than `staleMs` is left from a crash and is taken over. If the lock cannot be had in time (or at
 * all), `work` runs anyway: a lock must never block or fail a check.
 */
export function withLock(lockPath, work, waitMs = 2000, staleMs = 30_000) {
    const until = Date.now() + waitMs;
    const token = `${process.pid}.${randomBytes(8).toString("hex")}`;
    let held = false;
    for (let tries = 0; tries < 10_000; tries++) {
        try {
            const fd = openSync(lockPath, "wx", 0o600);
            try {
                writeSync(fd, token);
            }
            finally {
                closeSync(fd);
            }
            held = true;
            break;
        }
        catch (err) {
            if (err.code !== "EEXIST")
                break;
            if (takeStale(lockPath, staleMs))
                continue;
            if (Date.now() >= until)
                break;
            Atomics.wait(SLEEP, 0, 0, 10 + Math.floor(Math.random() * 15));
        }
    }
    try {
        return work();
    }
    finally {
        // Only our own lock is removed: if it was taken over meanwhile, the new one belongs to someone else.
        if (held)
            try {
                if (readFileSync(lockPath, "utf8") === token)
                    unlinkSync(lockPath);
            }
            catch { /* gone */ }
    }
}
export function stamp(date = new Date()) {
    return date.toISOString().replace(/[:.]/g, "-").replace("T", "_").slice(0, 19);
}
export function round(n, digits = 2) {
    const f = 10 ** digits;
    return Math.round(n * f) / f;
}
/** Run `work` over `items` with at most `limit` running at once; results keep the items' order. */
export async function pool(items, limit, work) {
    const results = new Array(items.length);
    let next = 0;
    const worker = async () => {
        while (next < items.length) {
            const i = next++;
            results[i] = await work(items[i], i);
        }
    };
    await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, worker));
    return results;
}
