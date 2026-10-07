import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, join, relative, sep } from "node:path";
import ts from "typescript";
const SKIP = new Set(["node_modules", ".git", "dist", "build", ".next", ".output", ".vinxi", ".lawha", "coverage", ".turbo"]);
function walk(dir, match, out = []) {
    let entries;
    try {
        entries = readdirSync(dir);
    }
    catch {
        return out;
    }
    for (const name of entries) {
        if (SKIP.has(name) || name.startsWith("."))
            continue;
        const path = join(dir, name);
        let st;
        try {
            st = statSync(path);
        }
        catch {
            continue;
        }
        if (st.isDirectory())
            walk(path, match, out);
        else if (match(path))
            out.push(path);
    }
    return out;
}
function read(path) {
    try {
        return readFileSync(path, "utf8");
    }
    catch {
        return "";
    }
}
/** Custom properties declared inside @theme { } and :root / .dark { } blocks. */
function cssTokens(file, text, root) {
    const tokens = [];
    const block = /(@theme(?:\s+inline)?|:root|\.dark|\[data-theme[^\]]*\])\s*\{([^}]*)\}/g;
    for (const m of text.matchAll(block)) {
        for (const d of (m[2] ?? "").matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
            tokens.push({ name: d[1], value: d[2].trim(), source: `${relative(root, file)} ${m[1]}` });
        }
    }
    return tokens;
}
function propsOf(checker, node) {
    const param = node.parameters[0];
    if (!param)
        return [];
    const type = checker.getTypeAtLocation(param);
    return type.getProperties().slice(0, 40).map((p) => {
        const decl = p.valueDeclaration ?? p.declarations?.[0];
        const t = decl ? checker.getTypeOfSymbolAtLocation(p, decl) : checker.getDeclaredTypeOfSymbol(p);
        return { name: p.getName(), type: checker.typeToString(t).slice(0, 120), optional: (p.getFlags() & ts.SymbolFlags.Optional) !== 0 };
    });
}
/** Exported, capitalised function components in .tsx files, with their props. */
function components(root, files) {
    const tsx = files.filter((f) => f.endsWith(".tsx") && !f.includes(`${sep}routes${sep}`)).slice(0, 400);
    if (!tsx.length)
        return [];
    const program = ts.createProgram(tsx, { jsx: ts.JsxEmit.ReactJSX, allowJs: false, skipLibCheck: true, noEmit: true, strict: false, target: ts.ScriptTarget.ES2022, moduleResolution: ts.ModuleResolutionKind.Bundler, module: ts.ModuleKind.ESNext });
    const checker = program.getTypeChecker();
    const out = [];
    for (const file of tsx) {
        const source = program.getSourceFile(file);
        if (!source)
            continue;
        const exported = (n) => ts.canHaveModifiers(n) && (ts.getModifiers(n) ?? []).some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
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
/** Props of a Vue single-file component: defineProps<{ ... }>() or defineProps({ name: Type }). */
function vueProps(text) {
    const typed = /defineProps\s*<\s*(\{[\s\S]*?\})\s*>\s*\(/.exec(text);
    if (typed) {
        const source = ts.createSourceFile("props.ts", `type P = ${typed[1]}`, ts.ScriptTarget.ES2022, true);
        const alias = source.statements[0];
        if (alias && ts.isTypeAliasDeclaration(alias) && ts.isTypeLiteralNode(alias.type)) {
            return alias.type.members.filter(ts.isPropertySignature).slice(0, 40).map((m) => ({ name: m.name.getText(source), type: m.type?.getText(source) ?? "unknown", optional: !!m.questionToken }));
        }
    }
    const runtime = /defineProps\s*\(\s*(\{[\s\S]*?\})\s*\)/.exec(text);
    if (runtime) {
        const source = ts.createSourceFile("props.ts", `const p = ${runtime[1]}`, ts.ScriptTarget.ES2022, true);
        const init = source.statements[0]?.declarationList.declarations[0]?.initializer;
        if (init && ts.isObjectLiteralExpression(init)) {
            return init.properties.filter(ts.isPropertyAssignment).slice(0, 40).map((p) => {
                const value = p.initializer;
                const typeOf = (e) => (e ? e.getText(source).toLowerCase() : "unknown");
                if (ts.isObjectLiteralExpression(value)) {
                    const field = (k) => value.properties.find((q) => ts.isPropertyAssignment(q) && q.name.getText(source) === k)?.initializer;
                    return { name: p.name.getText(source), type: typeOf(field("type")), optional: field("required")?.kind !== ts.SyntaxKind.TrueKeyword };
                }
                return { name: p.name.getText(source), type: typeOf(value), optional: true };
            });
        }
    }
    return [];
}
function vueComponents(root, files) {
    return files.filter((f) => f.endsWith(".vue")).slice(0, 400).map((f) => ({ name: basename(f, ".vue"), file: relative(root, f), props: vueProps(read(f)) }));
}
/** Tailwind 3 keeps its tokens in tailwind.config.*: theme values, read without running the file. */
function tailwindTokens(root) {
    const file = ["tailwind.config.ts", "tailwind.config.js", "tailwind.config.mjs", "tailwind.config.cjs"].map((n) => join(root, n)).find((p) => existsSync(p));
    if (!file)
        return [];
    const source = ts.createSourceFile(file, read(file), ts.ScriptTarget.ES2022, true);
    const tokens = [];
    const flatten = (node, path) => {
        for (const p of node.properties) {
            if (!ts.isPropertyAssignment(p) || tokens.length >= 300)
                continue;
            const key = ts.isStringLiteral(p.name) || ts.isIdentifier(p.name) || ts.isNumericLiteral(p.name) ? p.name.text : p.name.getText(source);
            const at = key === "extend" && path.length === 0 ? path : [...path, key];
            if (ts.isObjectLiteralExpression(p.initializer))
                flatten(p.initializer, at);
            else if (ts.isStringLiteralLike(p.initializer) || ts.isNumericLiteral(p.initializer))
                tokens.push({ name: at.join("."), value: p.initializer.text, source: relative(root, file) });
        }
    };
    const visit = (node) => {
        if (ts.isPropertyAssignment(node) && node.name.getText(source) === "theme" && ts.isObjectLiteralExpression(node.initializer))
            flatten(node.initializer, []);
        else
            ts.forEachChild(node, visit);
    };
    visit(source);
    return tokens;
}
/** Next.js routes: the app router's page files (route groups and slots left out) and the pages router. */
function nextRoutes(root) {
    const routes = [];
    for (const dir of [join(root, "app"), join(root, "src", "app")].filter((d) => existsSync(d))) {
        for (const page of walk(dir, (p) => /[\\/]page\.(tsx|ts|jsx|js|mdx)$/.test(p))) {
            const parts = relative(dir, page).split(sep).slice(0, -1).filter((s) => !/^\(.*\)$/.test(s) && !s.startsWith("@"));
            routes.push("/" + parts.join("/"));
        }
    }
    for (const dir of [join(root, "pages"), join(root, "src", "pages")].filter((d) => existsSync(d))) {
        for (const page of walk(dir, (p) => /\.(tsx|ts|jsx|js|mdx)$/.test(p))) {
            const parts = relative(dir, page).replace(/\.(tsx|ts|jsx|js|mdx)$/, "").split(sep);
            if (parts[0] === "api" || parts.some((s) => s.startsWith("_")))
                continue;
            if (parts.at(-1) === "index")
                parts.pop();
            routes.push("/" + parts.join("/"));
        }
    }
    return routes;
}
const HEX = /#[0-9a-fA-F]{3,8}\b/;
const ARBITRARY = /\b[\w:-]+-\[(\d+(?:\.\d+)?(?:px|rem|em))\]/;
const PHYSICAL = /(?<![\w-])(?:[\w-]+:)?(?:-?(?:ml|mr|pl|pr)-[\w./[\]-]+|text-(?:left|right)|(?:left|right)-[\w./[\]-]+|rounded-(?:l|r|tl|tr|bl|br)(?:-[\w-]+)?|border-(?:l|r)(?:-[\w-]+)?)(?![\w-])/;
function drift(root, files) {
    const out = [];
    for (const file of files.filter((f) => /\.(tsx|jsx|vue)$/.test(f))) {
        read(file).split("\n").forEach((line, i) => {
            if (out.length >= 200)
                return;
            const at = { file: relative(root, file), line: i + 1 };
            const classAttr = /className=|cn\(|clsx\(|cva\(|\bclass=|:class=/.test(line);
            if (HEX.test(line) && !line.trim().startsWith("//"))
                out.push({ ...at, kind: "hard-coded colour", text: line.trim().slice(0, 140) });
            if (classAttr && ARBITRARY.test(line))
                out.push({ ...at, kind: "arbitrary size", text: line.trim().slice(0, 140) });
            if (classAttr && PHYSICAL.test(line))
                out.push({ ...at, kind: "physical utility", text: line.trim().slice(0, 140) });
        });
    }
    return out;
}
export function indexProject(root) {
    const pkg = JSON.parse(read(join(root, "package.json")) || "{}");
    const deps = { ...pkg.dependencies, ...pkg.devDependencies };
    const dep = (name) => deps[name] ?? null;
    const src = existsSync(join(root, "src")) ? join(root, "src") : root;
    const files = walk(src, (p) => /\.(tsx|ts|jsx|css|vue)$/.test(p) && !p.endsWith(".d.ts"));
    const tokens = [...files.filter((f) => f.endsWith(".css")).flatMap((f) => cssTokens(f, read(f), root)), ...tailwindTokens(root)];
    const shadcnConfig = JSON.parse(read(join(root, "components.json")) || "null");
    const uiAlias = shadcnConfig?.aliases?.ui ?? "@/components/ui";
    const uiDir = [join(root, "src", "components", "ui"), join(root, uiAlias.replace(/^@\//, "src/")), join(root, "components", "ui")].find((d) => existsSync(d)) ?? null;
    const shadcn = {
        configured: !!shadcnConfig,
        uiDir: uiDir ? relative(root, uiDir) : null,
        components: uiDir ? readdirSync(uiDir).filter((n) => /\.(tsx|jsx)$/.test(n)).map((n) => n.replace(/\.(tsx|jsx)$/, "")).sort() : [],
    };
    const routesDir = join(src, "routes");
    const routes = [...new Set([
            ...(existsSync(routesDir) ? walk(routesDir, (p) => /\.(tsx|ts|jsx)$/.test(p)).map((p) => "/" + relative(routesDir, p).replace(/\.(tsx|ts|jsx)$/, "").split(sep).join("/")) : []),
            ...nextRoutes(root),
        ])].sort();
    const fonts = new Set();
    for (const name of Object.keys(deps))
        if (name.startsWith("@fontsource"))
            fonts.add(name);
    for (const f of files.filter((p) => p.endsWith(".css"))) {
        for (const m of read(f).matchAll(/font-family\s*:\s*["']?([^;"',]+)/g))
            fonts.add(m[1].trim());
    }
    return {
        root,
        stack: {
            react: dep("react"),
            next: dep("next"),
            vue: dep("vue"),
            tanstackRouter: dep("@tanstack/react-router"),
            tanstackStart: dep("@tanstack/react-start"),
            tailwind: dep("tailwindcss"),
            motion: dep("motion"),
            typescript: existsSync(join(root, "tsconfig.json")),
        },
        tokens,
        shadcn,
        components: [...components(root, files), ...vueComponents(root, files)].filter((c) => !uiDir || !c.file.startsWith(relative(root, uiDir))),
        routes,
        fonts: [...fonts],
        drift: drift(root, files),
    };
}
