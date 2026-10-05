# itqan pack: .NET / C#

Read the project's facts first: `TargetFramework`, `<Nullable>`, `<ImplicitUsings>`,
`<TreatWarningsAsErrors>` in the .csproj / `Directory.Build.props`; the test framework
(xUnit / NUnit / MSTest) and assertion library; DI setup in `Program.cs`; EF Core or Dapper.
Follow what the project already does over anything below.

## Implementing
- **Async all the way:** no `.Result`, `.Wait()` or `GetAwaiter().GetResult()` on tasks.
  Accept and pass a `CancellationToken` through public async methods. `async void` only for
  event handlers. `ConfigureAwait(false)` in library code, not in ASP.NET Core app code.
- **Nullability:** honour the annotations; never silence warnings with `!`. Validate inputs
  with `ArgumentNullException.ThrowIfNull(x)` / `ArgumentException.ThrowIfNullOrEmpty(s)`.
- **Disposal:** `using` / `await using` for `IDisposable` / `IAsyncDisposable`. `HttpClient`
  only via `IHttpClientFactory` or a typed client, never `new HttpClient()` per call.
- **Config:** `IOptions<T>` with validation (`ValidateDataAnnotations().ValidateOnStart()`);
  secrets from user-secrets / environment / a vault, never `appsettings.json` in git.
- **Logging:** `ILogger<T>` with message templates: `_log.LogInformation("Order {OrderId} paid", id)`,
  not string interpolation. Never log tokens, passwords or full request bodies.
- **Time and culture:** `TimeProvider` / `DateTimeOffset.UtcNow` (testable, no local time
  bugs). `StringComparison.Ordinal(IgnoreCase)` for identifiers; invariant culture for
  machine-readable formatting.
- **Types:** `record` for DTOs and value objects; immutable where possible; no public mutable
  static state.
- **LINQ:** don't enumerate an `IEnumerable` twice (materialize once); `Any()` instead of
  `Count() > 0`.

## EF Core
- `AsNoTracking()` for read-only queries; project to DTOs with `Select` instead of loading
  whole graphs; avoid N+1 (a query inside a loop) with `Include` or a single projection.
- Raw SQL only via `FromSql($"... {param}")` / parameters, never string concatenation.
- Review every migration: data loss (dropped columns), long locks on big tables, default values.

## ASP.NET Core
- A fallback authorization policy, or `[Authorize]` on every controller; check **ownership**,
  not just authentication (`order.UserId == currentUserId`).
- Validate input (data annotations / FluentValidation); return `ProblemDetails`; never return
  exception messages or stack traces to clients.
- CORS: no `AllowAnyOrigin()` together with credentials.

## Testing
- Names: `Method_Scenario_ExpectedResult`. Arrange / act / assert. One behaviour per test.
- Integration tests with `WebApplicationFactory<Program>`; real databases via Testcontainers
  if the project uses it; `FakeTimeProvider` for time.
- No `Thread.Sleep` / `Task.Delay` to wait for things; no shared mutable state between tests.

## Review checklist (bugs that bite)
- [ ] sync-over-async or a missing `await` (fire-and-forget task that swallows exceptions)
- [ ] `CancellationToken` accepted but not passed on
- [ ] null paths the annotations hide (`!`), `FirstOrDefault()` result used without a check
- [ ] disposable created and not disposed; `HttpClient` per request
- [ ] EF: tracking queries in read paths, N+1, client-side evaluation, missing transaction
      around multi-step writes
- [ ] endpoint without authorization or ownership check
- [ ] secrets or PII in logs, config or exceptions
- [ ] `DateTime.Now` in logic; culture-sensitive parsing/formatting of machine data
- [ ] new behaviour without a test

## Commands
`dotnet build -warnaserror` · `dotnet test --filter "FullyQualifiedName~OrderTests"` ·
`dotnet format --verify-no-changes` · with barq: `barq run:build run:test`
