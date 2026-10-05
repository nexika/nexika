# itqan pack: Node.js / TypeScript

Read the project's facts first: `package.json` (scripts, `type: module`?, engines), the
package manager (lockfile), `tsconfig.json` (`strict`?), the framework (Express, Fastify,
NestJS, Next.js, React, Vue), the test runner (Vitest, Jest, node:test, Playwright) and lint
setup. Follow what the project already does.

## Implementing
- **TypeScript:** keep `strict`; no `any` to silence errors (use `unknown` + narrowing);
  no non-null `!` without a reason; types for public functions; validate external input at
  the boundary (zod / valibot / class-validator) and use the inferred types inside.
- **Async:** always `await` or return promises; no floating promises (errors vanish);
  `Promise.all` for independent work; never `forEach(async ...)` (it doesn't wait).
- **Errors:** throw `Error` objects, not strings; keep the cause (`new Error(msg, { cause })`);
  one error handler per HTTP framework, not try/catch in every route.
- **Equality and nulls:** `===`; `??` instead of `||` for defaults when 0/"" are valid.
- **Config/secrets:** from the environment, validated at startup; `.env` never committed.
- **Dependencies:** prefer the platform (fetch, node:crypto, URL) over new packages; pin via
  the lockfile; don't edit the lockfile by hand.

## Security
- SQL via parameters / query builder / ORM, never template strings with input.
- No `eval`, `new Function`, or `child_process.exec` with input (use `execFile` with args).
- Path traversal: resolve and check paths built from input.
- Web: escape output (frameworks do, `dangerouslySetInnerHTML`/`v-html` don't); CSRF on cookie
  auth; CORS not `*` with credentials; helmet / security headers on Express.

## Frontend (React / Vue)
- Effects: complete dependency arrays; clean up subscriptions/timers; no data fetching races
  (abort or ignore stale responses).
- Keys: stable ids, not array indexes, for lists that change.
- State: derive instead of duplicating; don't mutate state or props.

## Testing
- Vitest/Jest: one behaviour per test; `describe` by unit; fake timers instead of waiting;
  mock at the network boundary (msw) rather than internal modules.
- Testing Library: query by role/label like a user, not by class names.

## Review checklist (bugs that bite)
- [ ] floating promise / missing `await` / `forEach(async)`
- [ ] `any`, unchecked casts (`as X`) or `!` hiding a real null case
- [ ] `||` default swallowing 0 / "" / false
- [ ] input not validated at the API boundary
- [ ] SQL/shell/HTML built from input
- [ ] effect without cleanup, missing deps, stale-response race
- [ ] new dependency that the platform already covers
- [ ] new behaviour without a test

## Commands
`npm test` / `pnpm test` · `npx tsc --noEmit` · `npm run lint` · with barq: `barq run:test run:build`
