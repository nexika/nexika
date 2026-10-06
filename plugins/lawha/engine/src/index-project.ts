import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import ts from "typescript";

const SKIP = new Set(["node_modules", ".git", "dist", "build", ".next", ".output", ".vinxi", ".lawha", "coverage", ".turbo"]);

function walk(dir: string, match: (path: string) => boolean, out: string[] = []): string[] {
  let entries: string[];
  try { entries = readdirSync(dir); } catch { return out; }
  for (const name of entries) {
    if (SKIP.has(name) || name.startsWith(".")) continue;
    const path = join(dir, name);
    let st;
    try { st = statSync(path); } catch { continue; }
    if (st.isDirectory()) walk(path, match, out);
    else if (match(path)) out.push(path);
  }
  return out;
}

function read(path: string): string {
  try { return readFileSync(path, "utf8"); } catch { return ""; }
}

export interface Token { name: string; value: string; source: string }
export interface Component { name: string; file: string; props: { name: string; type: string; optional: boolean }[] }
export interface Drift { file: string; line: number; kind: "hard-coded colour" | "arbitrary size" | "physical utility"; text: string }

export interface SystemIndex {
  root: string;
  stack: { react: string | null; tanstackRouter: string | null; tanstackStart: string | null; tailwind: string | null; motion: string | null; typescript: boolean };
  tokens: Token[];
  shadcn: { configured: boolean; uiDir: string | null; components: string[] };
  components: Component[];
  routes: string[];
  fonts: string[];
  drift: Drift[];
}

/** Custom properties declared inside @theme { } and :root / .dark { } blocks. */
function cssTokens(file: string, text: string, root: string): Token[] {
  const tokens: Token[] = [];
  const block = /(@theme(?:\s+inline)?|:root|\.dark|\[data-theme[^\]]*\])\s*\{([^}]*)\}/g;
  for (const m of text.matchAll(block)) {
    for (const d of (m[2] ?? "").matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      tokens.push({ name: d[1]!, value: d[2]!.trim(), source: `${relative(root, file)} ${m[1]}` });
    }
  }
  return tokens;
}

function propsOf(checker: ts.TypeChecker, node: ts.FunctionLikeDeclaration): Component["props"] {
  const param = node.parameters[0];
  if (!param) return [];
  const type = checker.getTypeAtLocation(param);
  return type.getProperties().slice(0, 40).map((p) => {
    const decl = p.valueDeclaration ?? p.declarations?.[0];
    const t = decl ? checker.getTypeOfSymbolAtLocation(p, decl) : checker.getDeclaredTypeOfSymbol(p);
    return { name: p.getName(), type: checker.typeToString(t).slice(0, 120), optional: (p.getFlags() & ts.SymbolFlags.Optional) !== 0 };
  });
}

/** Exported, capitalised function components in .tsx files, with their props. */
function components(root: string, files: string[]): Component[] {
  const tsx = files.filter((f) => f.endsWith(".tsx") && !f.includes(`${sep}routes${sep}`)).slice(0, 400);
  if (!tsx.length) return [];
  const program = ts.createProgram(tsx, { jsx: ts.JsxEmit.ReactJSX, allowJs: false, skipLibCheck: true, noEmit: true, strict: false, target: ts.ScriptTarget.ES2022, moduleResolution: ts.ModuleResolutionKind.Bundler, module: ts.ModuleKind.ESNext });
  const checker = program.getTypeChecker();
  const out: Component[] = [];
  for (const file of tsx) {
    const source = program.getSourceFile(file);
    if (!source) continue;
    const exported = (n: ts.Node) => ts.canHaveModifiers(n) && (ts.getModifiers(n) ?? []).some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
    source.forEachChild((node) => {
      if (ts.isFunctionDeclaration(node) && node.name && /^[A-Z]/.test(node.name.text) && exported(node)) {
        out.push({ name: node.name.text, file: relative(root, file), props: propsOf(checker, node) });
      }
      if (ts.isVariableStatement(node) && exported(node)) {
        for (const d of node.declarationList.declarations) {
          if (ts.isIdentifier(d.name) && /^[A-Z]/.test(d.name.text) && d.initializer && (ts.isArrowFunction(d.initializer) || ts.isFunctionExpression(d.initializer))) {
            out.push({ name: d.name.text, file: relative(root, file), props: propsOf(checker, d.initializer) });
          }
        }
      }
    });
  }
  return out;
}

const HEX = /#[0-9a-fA-F]{3,8}\b/;
const ARBITRARY = /\b[\w:-]+-\[(\d+(?:\.\d+)?(?:px|rem|em))\]/;
const PHYSICAL = /(?<![\w-])(?:[\w-]+:)?(?:-?(?:ml|mr|pl|pr)-[\w./[\]-]+|text-(?:left|right)|(?:left|right)-[\w./[\]-]+|rounded-(?:l|r|tl|tr|bl|br)(?:-[\w-]+)?|border-(?:l|r)(?:-[\w-]+)?)(?![\w-])/;

function drift(root: string, files: string[]): Drift[] {
  const out: Drift[] = [];
  for (const file of files.filter((f) => /\.(tsx|jsx)$/.test(f))) {
    read(file).split("\n").forEach((line, i) => {
      if (out.length >= 200) return;
      const at = { file: relative(root, file), line: i + 1 };
      const classAttr = /className=|cn\(|clsx\(|cva\(/.test(line);
      if (HEX.test(line) && !line.trim().startsWith("//")) out.push({ ...at, kind: "hard-coded colour", text: line.trim().slice(0, 140) });
      if (classAttr && ARBITRARY.test(line)) out.push({ ...at, kind: "arbitrary size", text: line.trim().slice(0, 140) });
      if (classAttr && PHYSICAL.test(line)) out.push({ ...at, kind: "physical utility", text: line.trim().slice(0, 140) });
    });
  }
  return out;
}

export function indexProject(root: string): SystemIndex {
  const pkg = JSON.parse(read(join(root, "package.json")) || "{}") as { dependencies?: Record<string, string>; devDependencies?: Record<string, string> };
  const deps = { ...pkg.dependencies, ...pkg.devDependencies };
  const dep = (name: string) => deps[name] ?? null;
  const src = existsSync(join(root, "src")) ? join(root, "src") : root;
  const files = walk(src, (p) => /\.(tsx|ts|jsx|css)$/.test(p) && !p.endsWith(".d.ts"));

  const tokens = files.filter((f) => f.endsWith(".css")).flatMap((f) => cssTokens(f, read(f), root));

  const shadcnConfig = JSON.parse(read(join(root, "components.json")) || "null") as { aliases?: { ui?: string } } | null;
  const uiAlias = shadcnConfig?.aliases?.ui ?? "@/components/ui";
  const uiDir = [join(root, "src", "components", "ui"), join(root, uiAlias.replace(/^@\//, "src/")), join(root, "components", "ui")].find((d) => existsSync(d)) ?? null;
  const shadcn = {
    configured: !!shadcnConfig,
    uiDir: uiDir ? relative(root, uiDir) : null,
    components: uiDir ? readdirSync(uiDir).filter((n) => /\.(tsx|jsx)$/.test(n)).map((n) => n.replace(/\.(tsx|jsx)$/, "")).sort() : [],
  };

  const routesDir = join(src, "routes");
  const routes = existsSync(routesDir)
    ? walk(routesDir, (p) => /\.(tsx|ts|jsx)$/.test(p)).map((p) => "/" + relative(routesDir, p).replace(/\.(tsx|ts|jsx)$/, "").split(sep).join("/")).sort()
    : [];

  const fonts = new Set<string>();
  for (const name of Object.keys(deps)) if (name.startsWith("@fontsource")) fonts.add(name);
  for (const f of files.filter((p) => p.endsWith(".css"))) {
    for (const m of read(f).matchAll(/font-family\s*:\s*["']?([^;"',]+)/g)) fonts.add(m[1]!.trim());
  }

  return {
    root,
    stack: {
      react: dep("react"),
      tanstackRouter: dep("@tanstack/react-router"),
      tanstackStart: dep("@tanstack/react-start"),
      tailwind: dep("tailwindcss"),
      motion: dep("motion"),
      typescript: existsSync(join(root, "tsconfig.json")),
    },
    tokens,
    shadcn,
    components: components(root, files).filter((c) => !uiDir || !c.file.startsWith(relative(root, uiDir))),
    routes,
    fonts: [...fonts],
    drift: drift(root, files),
  };
}
