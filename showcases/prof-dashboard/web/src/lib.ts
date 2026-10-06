import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// ---------------------------------------------------------------- session token and demo switch

/**
 * The server opens the page at /#t=TOKEN. The fragment never leaves the browser; the token is kept for
 * this tab only (sessionStorage, so a reload keeps working) and sent as a header on each API call.
 */
function readToken(): string {
  const hash = new URLSearchParams(location.hash.slice(1));
  const fromHash = hash.get("t");
  if (fromHash) {
    try { sessionStorage.setItem("prof-token", fromHash); } catch { /* private mode: memory only */ }
    history.replaceState(null, "", location.pathname + location.search);
    return fromHash;
  }
  try { return sessionStorage.getItem("prof-token") ?? ""; } catch { return ""; }
}

export const token = readToken();

export function demoOn(): boolean {
  if (new URLSearchParams(location.search).get("demo") === "1") return true;
  try { return localStorage.getItem("prof-demo") === "1"; } catch { return false; }
}

export function setDemo(on: boolean): void {
  try { localStorage.setItem("prof-demo", on ? "1" : "0"); } catch { /* ignore */ }
  const url = new URL(location.href);
  url.searchParams.delete("demo");
  location.replace(url.toString());
}

// ---------------------------------------------------------------- API

export type Status = "missed" | "shaky" | "not-checked" | "understood";
export interface Concept { topic: string; concept: string; status: Status; evidence: string; date: string; stale: boolean }
export type Counts = Record<Status | "stale", number>;
export interface Summary { today: { review: Concept[]; counts: Counts }; topics: number; sessions: number; last_session: string | null; has_data: boolean }
export interface TopicCard { slug: string; title: string; last: string; counts: Counts; mastery: number }
export interface Topic { slug: string; title: string; concepts: Concept[] }
export interface SessionCard { id: string; date: string; time: string; learned: string[]; review_next: string[] }
export interface Session {
  id: string; date: string; time: string;
  sections: { learned: string[]; did: string[]; checks: { q: string; answer: string; verdict: string }[]; weak: string[]; levels: string[]; review_next: string[]; checklist: Concept[] };
}
export type Localised = Partial<Record<"en" | "ar" | "fr", string>>;
export interface Course {
  available: boolean;
  course?: { id: string; title: Localised };
  modules: { id: string; level: number; title: Localised; lessons: { id: string; title: Localised; minutes: number | null; status: string }[] }[];
}

export async function api<T>(path: string): Promise<T> {
  const url = `/api/${path}${demoOn() ? "?demo=1" : ""}`;
  const response = await fetch(url, { headers: { "X-Lawha-Token": token } });
  if (response.status === 403) throw new Error("token");
  if (!response.ok) throw new Error(String(response.status));
  return (await response.json()) as T;
}

/** The kind of a concept as shown: stale wins over understood. */
export function kind(c: Concept): Status | "stale" {
  return c.status === "understood" && c.stale ? "stale" : c.status;
}
