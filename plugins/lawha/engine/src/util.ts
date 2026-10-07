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

/** Minimal flag parser: --name value, --name=value, --flag (boolean); a repeated flag collects its values. */
export function parseArgs(argv: string[], booleans: string[] = [], repeated: string[] = []): Args {
  const out: Args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i] as string;
    if (!arg.startsWith("--")) {
      out._.push(arg);
      continue;
    }
    const cut = arg.indexOf("=");
    const name = cut < 0 ? arg.slice(2) : arg.slice(2, cut);
    const inline = cut < 0 ? undefined : arg.slice(cut + 1);
    const value = inline !== undefined ? inline : booleans.includes(name) ? true : (argv[++i] ?? "");
    if (repeated.includes(name)) out[name] = [...((out[name] as string[] | undefined) ?? []), String(value)];
    else out[name] = value;
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
