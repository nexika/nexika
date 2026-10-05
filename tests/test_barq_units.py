"""barq building blocks: secret masking, outlines/symbols, and test/build output parsing."""
from __future__ import annotations

import textwrap

import pytest
from barq import compress
from barq.mask import MASK, mask_text
from barq.outline import find_symbol, outline

# ---------------------------------------------------------------- masking


@pytest.mark.parametrize("secret", [
    "ghp_" + "a" * 36,
    "github_pat_" + "B" * 50,
    "glpat-" + "c" * 20,
    "sk-ant-api03-" + "d" * 30,
    "AKIA" + "E" * 16,
    "xoxb-1234567890-abcdef",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
])
def test_known_tokens_are_masked_anywhere(secret):
    text, n = mask_text(f"log: using {secret} now")
    assert secret not in text and MASK in text and n == 1


def test_private_key_block_and_url_credentials():
    key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"
    text, _ = mask_text(
        f"{key}\npostgres://admin:hunter2@db:5432/x\nAuthorization: Bearer abcdefghijklmnopqrstu"
    )
    assert "MIIEow" not in text and "hunter2" not in text and "abcdefghijklmnop" not in text
    assert "postgres://admin:[masked]@db" in text


def test_env_file_masks_every_value_but_keeps_comments():
    text, n = mask_text("# db settings\nDB_HOST=localhost\nexport PORT=5432\nEMPTY=\"\"\n", ".env")
    assert text.splitlines() == ["# db settings", "DB_HOST=[masked]", "export PORT=[masked]", 'EMPTY=""']
    assert n == 2


def test_env_example_is_not_fully_masked():
    text, _ = mask_text("DB_HOST=localhost\n", ".env.example")
    assert "localhost" in text


@pytest.mark.parametrize(("line", "masked"), [
    ('password = "s3cr3t-value"', True),          # quoted literal
    ("Server=db;Password=abc123;", True),          # connection string
    ("API_KEY: Zx81kLmn0pQrStUv", True),           # long, secret-looking
    ("password: str", False),                      # type hint
    ("token = get_token()", False),                # code, not a value
    ("secret_name = read_secret_name", False),     # identifier
])
def test_assignments(line, masked):
    text, _ = mask_text(line)
    assert (MASK in text) is masked, text


def test_config_files_mask_secret_keys():
    text, _ = mask_text('{"ConnectionStrings": {"Main": "x"}, "ClientSecret": "plainvalue"}',
                        "appsettings.json")
    assert "plainvalue" not in text


def test_masking_can_be_disabled(monkeypatch):
    monkeypatch.setenv("BARQ_NO_MASK", "1")
    assert mask_text("ghp_" + "a" * 36)[1] == 0


# ---------------------------------------------------------------- outlines


PY = textwrap.dedent('''\
    import os

    @dataclass
    class Cart:
        items: list

        def total(self) -> int:
            return sum(self.items)

        @staticmethod
        async def load(path: str):
            return Cart([])

    def helper(x, *, y=1):
        def inner():
            pass
        return x
''')


def test_python_outline_and_symbols():
    syms = {s.name: s for s in outline(PY, ".py")}
    assert list(syms) == ["Cart", "Cart.total", "Cart.load", "helper"]
    assert (syms["Cart"].line, syms["Cart"].end) == (3, 12)          # includes @dataclass
    assert syms["Cart.load"].line == 10                               # includes @staticmethod
    assert syms["Cart.load"].signature == "async def load(path: str)"
    assert syms["Cart.total"].signature == "def total(self) -> int"
    assert [s.name for s in find_symbol(PY, ".py", "load")] == ["Cart.load"]
    assert [s.name for s in find_symbol(PY, ".py", "cart.TOTAL")] == ["Cart.total"]


def test_python_syntax_error_falls_back_to_indentation():
    broken = "def ok():\n    return 1\n\ndef broken(:\n    pass\n"
    assert [s.name for s in outline(broken, ".py")] == ["ok", "broken"]


CS = textwrap.dedent('''\
    using System;

    namespace Shop.Services
    {
        /// <summary>Handles users.</summary>
        public class UserService : IUserService
        {
            private readonly string _greeting = "Hello { not a brace";

            public UserService(ILogger logger)
            {
                _logger = logger;
            }

            [HttpGet]
            public async Task<User> LoginAsync(string name, string password)
            {
                if (name == null)
                {
                    throw new ArgumentNullException(nameof(name));
                }
                var user = await _repo.FindAsync(name);
                return Map(user);
            }

            public int Count => _users.Count;

            private static User Map(User u) => u;
        }

        public interface IUserService
        {
            Task<User> LoginAsync(string name, string password);
        }
    }
''')


def test_csharp_outline():
    syms = outline(CS, ".cs")
    names = [s.name for s in syms]
    assert names == [
        "Shop", "Shop.UserService", "Shop.UserService.UserService", "Shop.UserService.LoginAsync",
        "Shop.UserService.Map", "Shop.IUserService", "Shop.IUserService.LoginAsync",
    ]
    by_name = {s.name: s for s in syms}
    login = by_name["Shop.UserService.LoginAsync"]
    assert (login.line, login.end) == (15, 24)          # [HttpGet] .. closing brace
    assert by_name["Shop.UserService.Map"].line == by_name["Shop.UserService.Map"].end
    assert by_name["Shop.UserService"].line == 5        # doc comment included
    assert by_name["Shop.UserService"].end == 29


def test_csharp_find_symbol_qualified():
    found = find_symbol(CS, ".cs", "UserService.LoginAsync")
    assert [s.name for s in found] == ["Shop.UserService.LoginAsync"]
    assert len(find_symbol(CS, ".cs", "LoginAsync")) == 2


TS = textwrap.dedent('''\
    export interface User { id: number }
    export class Api {
      constructor(private base: string) {}
      async get(path: string): Promise<User> {
        const res = await fetch(this.base + path);
        return res.json();
      }
    }
    const add = (a: number, b: number) => a + b;
    export function main() {
      console.log(add(1, 2));
    }
''')


def test_typescript_outline():
    assert [s.name for s in outline(TS, ".ts")] == [
        "User", "Api", "Api.constructor", "Api.get", "add", "main",
    ]


GO = textwrap.dedent('''\
    package main

    type Server struct {
    \taddr string
    }

    func (s *Server) Start() error {
    \treturn nil
    }

    func main() {
    \ts := &Server{}
    \ts.Start()
    }
''')


def test_go_outline():
    syms = {s.name: s for s in outline(GO, ".go")}
    assert list(syms) == ["Server", "Start", "main"]
    assert syms["Start"].kind == "method" and (syms["Start"].line, syms["Start"].end) == (7, 9)


def test_markdown_sections_skip_code_fences():
    md = "# Title\nintro\n## Setup\nsteps\n```\n# not a heading\n```\n## Usage\ntext\n"
    syms = {s.name: s for s in outline(md, ".md")}
    assert list(syms) == ["Title", "Setup", "Usage"]
    assert (syms["Setup"].line, syms["Setup"].end) == (3, 7)


def test_unsupported_language():
    assert outline("x", ".txt") is None


# ---------------------------------------------------------------- output parsing


def summarize(text, rc=1):
    verdict, details, raw = compress.summarize(textwrap.dedent(text), rc)
    return verdict, "\n".join(details), raw


def test_pytest_output():
    verdict, details, _ = summarize("""\
        ============================= test session starts ==============================
        collected 3 items

        tests/test_a.py .F.                                                      [100%]

        =================================== FAILURES ===================================
        _________________________________ test_add ____________________________________

            def test_add():
        >       assert add(1, 2) == 4
        E       assert 3 == 4

        tests/test_a.py:5: AssertionError
        =========================== short test summary info ============================
        FAILED tests/test_a.py::test_add - assert 3 == 4
        ========================= 1 failed, 2 passed in 0.05s ==========================
    """)
    assert verdict == "1 failed, 2 passed in 0.05s"
    assert "FAILED tests/test_a.py::test_add - assert 3 == 4" in details
    assert "E       assert 3 == 4" in details
    assert "tests/test_a.py:5: AssertionError" in details
    assert "test session starts" not in details


def test_dotnet_test_output():
    verdict, details, _ = summarize("""\
          Determining projects to restore...
          Shop -> /src/Shop/bin/Debug/net8.0/Shop.dll
        Starting test execution, please wait...
          Failed Shop.Tests.CartTests.Total_SumsItems [12 ms]
          Error Message:
           Assert.Equal() Failure: Values differ
        Expected: 30
        Actual:   20
          Stack Trace:
             at Shop.Tests.CartTests.Total_SumsItems() in /src/Shop.Tests/CartTests.cs:line 14
           at System.RuntimeMethodHandle.InvokeMethod(Object target, Void** arguments)

        Failed!  - Failed:     1, Passed:     7, Skipped:     0, Total:     8, Duration: 52 ms
    """)
    assert verdict.startswith("Failed!  - Failed:     1, Passed:     7")
    assert "FAILED Shop.Tests.CartTests.Total_SumsItems" in details
    assert "Expected: 30" in details and "Actual:   20" in details
    assert "CartTests.cs:line 14" in details
    assert "InvokeMethod" not in details and "Determining" not in details


def test_dotnet_build_dedupes_and_strips_project_suffix():
    verdict, details, _ = summarize("""\
        /src/Shop/Cart.cs(12,20): error CS0103: The name 'totl' does not exist [/src/Shop/Shop.csproj]
        /src/Shop/Cart.cs(3,7): warning CS8019: Unnecessary using directive. [/src/Shop/Shop.csproj]

        Build FAILED.

        /src/Shop/Cart.cs(12,20): error CS0103: The name 'totl' does not exist [/src/Shop/Shop.csproj]
        /src/Shop/Cart.cs(3,7): warning CS8019: Unnecessary using directive. [/src/Shop/Shop.csproj]
            1 Warning(s)
            1 Error(s)
    """)
    assert verdict == "Build FAILED: 1 error(s), 1 warning(s)"
    assert details.splitlines() == [
        "/src/Shop/Cart.cs(12,20): error CS0103: The name 'totl' does not exist",
        "/src/Shop/Cart.cs(3,7): warning CS8019: Unnecessary using directive.",
    ]


def test_tsc_is_not_mistaken_for_msbuild():
    verdict, _, _ = summarize("src/a.ts(3,5): error TS2322: Type 'string' is not assignable.\n")
    assert verdict == "TypeScript: 1 error(s)"


def test_go_test_output():
    verdict, details, _ = summarize("""\
        --- FAIL: TestAdd (0.00s)
            math_test.go:9: expected 4, got 3
        FAIL
        FAIL\texample.com/m\t0.002s
        ok  \texample.com/m/util\t0.001s
    """)
    assert verdict == "go test: 1 failed"
    assert "math_test.go:9: expected 4, got 3" in details


def test_cargo_test_output():
    verdict, details, _ = summarize("""\
        running 2 tests
        test tests::subs ... FAILED

        failures:

        ---- tests::subs stdout ----
        thread 'tests::subs' panicked at src/lib.rs:12:9:
        assertion `left == right` failed

        test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out
    """)
    assert verdict.startswith("test result: FAILED. 1 passed; 1 failed")
    assert "panicked at src/lib.rs:12:9" in details


def test_jest_output():
    verdict, details, _ = summarize("""\
         FAIL  src/sum.test.js
          ● sum › adds numbers
            Expected: 4
            Received: 3
        Tests:       1 failed, 3 passed, 4 total
    """)
    assert "1 failed, 3 passed" in verdict
    assert "● sum › adds numbers" in details and "Received: 3" in details


def test_generic_failure_keeps_errors_and_tail():
    noise = "".join(f"step {i}\n" for i in range(200))
    verdict, details, raw = compress.summarize(noise + "Error: boom\nmore\n", 2)
    text = "\n".join(details)
    assert verdict == "failed" and "Error: boom" in text and raw == 202
    assert len(details) < 25


def test_generic_success_and_plain_error_lines_are_not_cargo():
    assert compress.summarize("error: config not found\n", 1)[0] == "failed"
    assert compress.summarize("all good\n", 0)[0] == "ok"


def test_ansi_codes_are_removed():
    assert compress.clean("\x1b[31mred\x1b[0m\r\n") == "red\n"
