import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export const DEFAULT_WIDTHS = [360, 390, 768, 1024, 1280, 1536];
export const PHONE_MAX = 767;

export type Severity = "fail" | "warn" | "info";

export interface Finding {
  check: string;
  severity: Severity;
  message: string;
  width?: number;
  theme?: string;
  dir?: string;
  motion?: string;
  selector?: string;
  box?: Box;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Args {
  _: string[];
  [flag: string]: string | boolean | string[];
}

/** Minimal flag parser: --name value, --name=value, --flag (boolean). */
export function parseArgs(argv: string[], booleans: string[] = []): Args {
  const out: Args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i] as string;
    if (!arg.startsWith("--")) {
      out._.push(arg);
      continue;
    }
    const [name, inline] = arg.slice(2).split("=", 2) as [string, string | undefined];
    if (inline !== undefined) out[name] = inline;
    else if (booleans.includes(name)) out[name] = true;
    else out[name] = argv[++i] ?? "";
  }
  return out;
}

export function list(value: string | boolean | string[] | undefined, fallback: string[]): string[] {
  if (typeof value !== "string" || !value.trim()) return fallback;
  return value.split(",").map((v) => v.trim()).filter(Boolean);
}

export function writeJson(path: string, data: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(data, null, 2) + "\n", "utf8");
}

export function stamp(date = new Date()): string {
  return date.toISOString().replace(/[:.]/g, "-").replace("T", "_").slice(0, 19);
}

export function round(n: number, digits = 2): number {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}
