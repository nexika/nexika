# itqan pack: Go

Read the project's facts first: the Go version in `go.mod`, the module layout (`cmd/`,
`internal/`, `pkg/`), the HTTP router, database access (database/sql, sqlx, pgx, an ORM),
logging (`log/slog`?), and lint config (`golangci-lint`). Follow what the project does.

## Implementing
- **Errors:** always handle them; wrap with context `fmt.Errorf("load user %d: %w", id, err)`;
  compare with `errors.Is` / `errors.As`, never by string; don't log *and* return the same error.
- **Context:** `ctx context.Context` as the first parameter of anything that does I/O; pass it
  on; respect cancellation; never store it in a struct.
- **Concurrency:** every goroutine has an owner and a way to stop; use `errgroup` for groups;
  protect shared state (mutex or channels) and run tests with `-race`; close channels from the
  sender only.
- **Resources:** `defer rows.Close()` / `resp.Body.Close()` right after checking the error;
  check `rows.Err()` after the loop.
- **HTTP:** clients with timeouts (never `http.DefaultClient` for external calls); servers with
  read/write timeouts.
- **Design:** small interfaces defined by the consumer; return concrete types; zero values
  that are useful; no package-level mutable state.

## Security
- SQL with placeholders (`$1` / `?`), never `fmt.Sprintf` with input.
- `os/exec` with an argument list, never `sh -c` with input.
- `filepath.Clean` + prefix check (or `os.Root` on new Go) for paths from input.
- `crypto/rand` for tokens, never `math/rand`.

## Testing
- Table-driven tests with `t.Run(tc.name, ...)`; `t.Helper()` in helpers; `t.TempDir()`,
  `t.Setenv()`; `httptest` for HTTP; run with `-race`.
- Compare with `cmp.Diff` or the project's assertion library; test errors with `errors.Is`.

## Review checklist (bugs that bite)
- [ ] ignored error (`_ =` or unchecked return)
- [ ] goroutine leak: no cancellation, blocked send, missing `wg.Wait`
- [ ] data race on shared map/slice; loop variable captured (pre-Go 1.22 modules)
- [ ] `defer` inside a loop holding resources until the function returns
- [ ] missing `rows.Err()` / unclosed bodies
- [ ] context not passed through; `context.Background()` deep in request code
- [ ] HTTP client without timeout; SQL/exec built from input
- [ ] new behaviour without a test

## Commands
`go build ./...` · `go test -race ./...` · `go vet ./...` · `golangci-lint run` ·
with barq: `barq run:build run:test`
