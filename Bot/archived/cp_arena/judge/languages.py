"""Supported programming languages, compilation commands, and execution wrappers.

Full suite of 16 languages supported with top-5 priority:
1. C++        → GNU++17 / GNU++20 / GNU++23
2. Python     → CPython 3.x
3. PyPy       → PyPy 3
4. Java       → Java 17+
5. C          → GCC
Plus: C# (.NET), Kotlin, Rust, Go, JavaScript, Pascal, Swift, Ruby, D, Scala, Haskell.
"""

from dataclasses import dataclass


@dataclass
class LanguageConfig:
    """Cấu hình chi tiết cho từng ngôn ngữ lập trình trong Sandbox Judge."""

    id: str
    name: str
    category: str
    aliases: list[str]
    source_filename: str
    is_compiled: bool
    compile_cmd: list[str] | None
    run_cmd: list[str]
    time_multiplier: float = 1.0
    memory_multiplier: float = 1.0
    is_top_priority: bool = False


# Danh mục toàn bộ 16 ngôn ngữ lập trình chuẩn thi đấu Codeforces
SUPPORTED_LANGUAGES: dict[str, LanguageConfig] = {
    # ── 1. C++ (GNU++17 / GNU++20 / GNU++23) ──
    "cpp17": LanguageConfig(
        id="cpp17",
        name="C++ (GNU++17)",
        category="C++",
        aliases=["cpp", "c++", "c++17", "g++", "g++17", "gnu++17"],
        source_filename="solution.cpp",
        is_compiled=True,
        compile_cmd=[
            "g++",
            "-O3",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "solution.cpp",
            "-o",
            "solution",
        ],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
        is_top_priority=True,
    ),
    "cpp20": LanguageConfig(
        id="cpp20",
        name="C++ (GNU++20)",
        category="C++",
        aliases=["c++20", "cpp20", "g++20", "gnu++20"],
        source_filename="solution.cpp",
        is_compiled=True,
        compile_cmd=[
            "g++",
            "-O3",
            "-std=c++20",
            "-Wall",
            "-Wextra",
            "solution.cpp",
            "-o",
            "solution",
        ],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
        is_top_priority=True,
    ),
    "cpp23": LanguageConfig(
        id="cpp23",
        name="C++ (GNU++23)",
        category="C++",
        aliases=["c++23", "cpp23", "g++23", "gnu++23"],
        source_filename="solution.cpp",
        is_compiled=True,
        compile_cmd=[
            "g++",
            "-O3",
            "-std=c++23",
            "-Wall",
            "-Wextra",
            "solution.cpp",
            "-o",
            "solution",
        ],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
        is_top_priority=True,
    ),
    # ── 2. Python (CPython 3.x) ──
    "python3": LanguageConfig(
        id="python3",
        name="Python (CPython 3.x)",
        category="Python",
        aliases=["python", "py", "python3", "py3", "cpython", "cpython3"],
        source_filename="solution.py",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["python3", "solution.py"],
        time_multiplier=2.0,
        memory_multiplier=1.5,
        is_top_priority=True,
    ),
    # ── 3. PyPy (PyPy 3) ──
    "pypy3": LanguageConfig(
        id="pypy3",
        name="PyPy (PyPy 3.x JIT)",
        category="PyPy",
        aliases=["pypy", "pypy3", "pypy3.10", "pypy-3"],
        source_filename="solution.py",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["pypy3", "solution.py"],
        time_multiplier=1.5,
        memory_multiplier=2.0,
        is_top_priority=True,
    ),
    # ── 4. Java (Java 17+) ──
    "java": LanguageConfig(
        id="java",
        name="Java (Java 17+ OpenJDK)",
        category="Java",
        aliases=["java", "java17", "java21", "openjdk", "jdk"],
        source_filename="Solution.java",
        is_compiled=True,
        compile_cmd=["javac", "Solution.java"],
        run_cmd=["java", "-Xmx256m", "-Xss64m", "Solution"],
        time_multiplier=1.5,
        memory_multiplier=2.0,
        is_top_priority=True,
    ),
    # ── 5. C (GCC) ──
    "c": LanguageConfig(
        id="c",
        name="C (GCC 17/11)",
        category="C",
        aliases=["c", "gcc", "c11", "c17", "c99", "gnuc"],
        source_filename="solution.c",
        is_compiled=True,
        compile_cmd=[
            "gcc",
            "-O3",
            "-std=c17",
            "-Wall",
            "-Wextra",
            "solution.c",
            "-o",
            "solution",
        ],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
        is_top_priority=True,
    ),
    # ── 6. C# (.NET) ──
    "csharp": LanguageConfig(
        id="csharp",
        name="C# (.NET)",
        category="C#",
        aliases=["c#", "cs", "csharp", "dotnet"],
        source_filename="Solution.cs",
        is_compiled=True,
        compile_cmd=["mcs", "Solution.cs", "-out:Solution.exe"],
        run_cmd=["mono", "Solution.exe"],
        time_multiplier=1.5,
        memory_multiplier=1.5,
    ),
    # ── 7. Kotlin (Kotlin/JVM) ──
    "kotlin": LanguageConfig(
        id="kotlin",
        name="Kotlin (Kotlin/JVM)",
        category="Kotlin",
        aliases=["kotlin", "kt", "kotlinc"],
        source_filename="solution.kt",
        is_compiled=True,
        compile_cmd=[
            "kotlinc",
            "solution.kt",
            "-include-runtime",
            "-d",
            "solution.jar",
        ],
        run_cmd=["java", "-jar", "solution.jar"],
        time_multiplier=1.5,
        memory_multiplier=2.0,
    ),
    # ── 8. Rust (rustc) ──
    "rust": LanguageConfig(
        id="rust",
        name="Rust (rustc 2021)",
        category="Rust",
        aliases=["rust", "rs", "rustc"],
        source_filename="solution.rs",
        is_compiled=True,
        compile_cmd=["rustc", "-O", "--edition=2021", "solution.rs", "-o", "solution"],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 9. Go (Go) ──
    "go": LanguageConfig(
        id="go",
        name="Go (Golang)",
        category="Go",
        aliases=["go", "golang"],
        source_filename="solution.go",
        is_compiled=True,
        compile_cmd=["go", "build", "-o", "solution", "solution.go"],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 10. JavaScript (Node.js) ──
    "javascript": LanguageConfig(
        id="javascript",
        name="JavaScript (Node.js)",
        category="JavaScript",
        aliases=["js", "javascript", "node", "nodejs"],
        source_filename="solution.js",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["node", "solution.js"],
        time_multiplier=1.5,
        memory_multiplier=1.5,
    ),
    # ── 11. Pascal (Free Pascal) ──
    "pascal": LanguageConfig(
        id="pascal",
        name="Pascal (Free Pascal FPC)",
        category="Pascal",
        aliases=["pascal", "pas", "fpc", "freepascal"],
        source_filename="solution.pas",
        is_compiled=True,
        compile_cmd=["fpc", "-O3", "solution.pas", "-osolution"],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 12. Lua (Lua 5.4 / LuaJIT) [MỚI] ──
    "lua": LanguageConfig(
        id="lua",
        name="Lua (Lua 5.4 / LuaJIT)",
        category="Lua",
        aliases=["lua", "luajit", "lua5.4", "lua54", "lua53"],
        source_filename="solution.lua",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["lua", "solution.lua"],
        time_multiplier=2.0,
        memory_multiplier=1.5,
    ),
    # ── 13. Swift (Swift) ──
    "swift": LanguageConfig(
        id="swift",
        name="Swift",
        category="Swift",
        aliases=["swift", "swiftc"],
        source_filename="solution.swift",
        is_compiled=True,
        compile_cmd=["swiftc", "-O", "solution.swift", "-o", "solution"],
        run_cmd=["./solution"],
        time_multiplier=1.5,
        memory_multiplier=1.5,
    ),
    # ── 14. Ruby (Ruby) ──
    "ruby": LanguageConfig(
        id="ruby",
        name="Ruby",
        category="Ruby",
        aliases=["ruby", "rb"],
        source_filename="solution.rb",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["ruby", "solution.rb"],
        time_multiplier=2.0,
        memory_multiplier=1.5,
    ),
    # ── 15. D (DMD/LDC) ──
    "d": LanguageConfig(
        id="d",
        name="D (DMD/LDC)",
        category="D",
        aliases=["d", "dmd", "ldc"],
        source_filename="solution.d",
        is_compiled=True,
        compile_cmd=["dmd", "-O", "-release", "solution.d", "-of=solution"],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 16. Scala (Scala/JVM) ──
    "scala": LanguageConfig(
        id="scala",
        name="Scala (Scala/JVM)",
        category="Scala",
        aliases=["scala", "scalac"],
        source_filename="Solution.scala",
        is_compiled=True,
        compile_cmd=["scalac", "Solution.scala"],
        run_cmd=["scala", "Solution"],
        time_multiplier=1.5,
        memory_multiplier=2.0,
    ),
    # ── 17. Haskell (GHC) ──
    "haskell": LanguageConfig(
        id="haskell",
        name="Haskell (GHC)",
        category="Haskell",
        aliases=["haskell", "hs", "ghc"],
        source_filename="solution.hs",
        is_compiled=True,
        compile_cmd=["ghc", "-O2", "solution.hs", "-o", "solution"],
        run_cmd=["./solution"],
        time_multiplier=1.5,
        memory_multiplier=1.5,
    ),
    # ── 18. OCaml (ocamlopt) [Ngách CP Thuật Toán] ──
    "ocaml": LanguageConfig(
        id="ocaml",
        name="OCaml (ocamlopt)",
        category="OCaml",
        aliases=["ocaml", "ml", "ocamlopt"],
        source_filename="solution.ml",
        is_compiled=True,
        compile_cmd=["ocamlopt", "-O3", "solution.ml", "-o", "solution"],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 19. Nim (nim c) [Ngách CP Thuật Toán] ──
    "nim": LanguageConfig(
        id="nim",
        name="Nim (nim c)",
        category="Nim",
        aliases=["nim", "nimrod"],
        source_filename="solution.nim",
        is_compiled=True,
        compile_cmd=[
            "nim",
            "c",
            "-d:release",
            "--opt:speed",
            "-o:solution",
            "solution.nim",
        ],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 20. Zig (zig build-exe) [Ngách Hệ Thống / Thuật Toán] ──
    "zig": LanguageConfig(
        id="zig",
        name="Zig (zig)",
        category="Zig",
        aliases=["zig"],
        source_filename="solution.zig",
        is_compiled=True,
        compile_cmd=[
            "zig",
            "build-exe",
            "-O",
            "ReleaseFast",
            "solution.zig",
            "-femit-bin=solution",
        ],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 21. Julia [Ngách Toán / Giải Thuật] ──
    "julia": LanguageConfig(
        id="julia",
        name="Julia",
        category="Julia",
        aliases=["julia", "jl"],
        source_filename="solution.jl",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["julia", "-O3", "solution.jl"],
        time_multiplier=2.0,
        memory_multiplier=2.0,
    ),
    # ── 22. TypeScript (Node.js) ──
    "typescript": LanguageConfig(
        id="typescript",
        name="TypeScript (Node.js)",
        category="TypeScript",
        aliases=["ts", "typescript", "tsx"],
        source_filename="solution.ts",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["npx", "ts-node", "solution.ts"],
        time_multiplier=1.5,
        memory_multiplier=1.5,
    ),
    # ── 23. Fortran (GNU Fortran) [Ngách Số Học] ──
    "fortran": LanguageConfig(
        id="fortran",
        name="Fortran (GNU Fortran)",
        category="Fortran",
        aliases=["fortran", "f90", "f95", "gfortran"],
        source_filename="solution.f90",
        is_compiled=True,
        compile_cmd=["gfortran", "-O3", "solution.f90", "-o", "solution"],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 24. Ada (GNAT) [Ngách An Toàn] ──
    "ada": LanguageConfig(
        id="ada",
        name="Ada (GNAT)",
        category="Ada",
        aliases=["ada", "adb", "gnat"],
        source_filename="solution.adb",
        is_compiled=True,
        compile_cmd=["gnatmake", "-O3", "solution.adb", "-o", "solution"],
        run_cmd=["./solution"],
        time_multiplier=1.0,
        memory_multiplier=1.0,
    ),
    # ── 25. PHP ──
    "php": LanguageConfig(
        id="php",
        name="PHP",
        category="PHP",
        aliases=["php", "php8"],
        source_filename="solution.php",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["php", "solution.php"],
        time_multiplier=1.5,
        memory_multiplier=1.5,
    ),
    # ── 26. Perl ──
    "perl": LanguageConfig(
        id="perl",
        name="Perl",
        category="Perl",
        aliases=["perl", "pl"],
        source_filename="solution.pl",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["perl", "solution.pl"],
        time_multiplier=2.0,
        memory_multiplier=1.5,
    ),
    # ── 27. Racket / Scheme [Ngách Hàm Lisp] ──
    "racket": LanguageConfig(
        id="racket",
        name="Racket / Scheme",
        category="Racket",
        aliases=["racket", "rkt", "scheme"],
        source_filename="solution.rkt",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["racket", "solution.rkt"],
        time_multiplier=2.0,
        memory_multiplier=2.0,
    ),
    # ── 28. Elixir ──
    "elixir": LanguageConfig(
        id="elixir",
        name="Elixir",
        category="Elixir",
        aliases=["elixir", "ex", "exs"],
        source_filename="solution.exs",
        is_compiled=False,
        compile_cmd=None,
        run_cmd=["elixir", "solution.exs"],
        time_multiplier=2.0,
        memory_multiplier=2.0,
    ),
}

# 1. 🌟 Nhóm 1: Top 5 Ngôn Ngữ Trọng Tâm Hàng Đầu (C++, Python, PyPy, Java, C)
TOP_PRIORITY_LANGUAGES = [
    lang for lang in SUPPORTED_LANGUAGES.values() if lang.is_top_priority
]

# 2. ⚡ Nhóm 2: 5 Ngôn Ngữ Thứ Cấp / Ít Dùng Hơn (C#, Kotlin, Rust, Go, Pascal)
SECONDARY_LANGUAGES = [
    SUPPORTED_LANGUAGES[k] for k in ["csharp", "kotlin", "rust", "go", "pascal"]
]

# 3. 🌐 Nhóm 3: Các Ngôn Ngữ Mở Rộng & Niche Giải Thuật (Lua, OCaml, Nim, Zig, Julia, TS, Swift, Ruby, D, Scala, Haskell, Fortran, Ada, PHP, Perl, Racket, Elixir)
EXTENDED_LANGUAGES = [
    lang
    for lang in SUPPORTED_LANGUAGES.values()
    if not lang.is_top_priority and lang not in SECONDARY_LANGUAGES
]

# Danh mục riêng cho các ngôn ngữ ngách thuật toán
NICHE_ALGORITHMIC_LANGUAGES = [
    SUPPORTED_LANGUAGES[k]
    for k in [
        "ocaml",
        "nim",
        "zig",
        "julia",
        "typescript",
        "fortran",
        "ada",
        "php",
        "perl",
        "racket",
        "elixir",
    ]
]


def get_language_by_alias(alias: str) -> LanguageConfig | None:
    """Tìm LanguageConfig tương ứng dựa trên ID hoặc Alias (không phân biệt hoa thường)."""
    clean_alias = alias.strip().lower()
    for lang in SUPPORTED_LANGUAGES.values():
        if lang.id.lower() == clean_alias or clean_alias in [
            a.lower() for a in lang.aliases
        ]:
            return lang
    return None


def get_supported_languages_list() -> list[LanguageConfig]:
    """Trả về danh sách toàn bộ ngôn ngữ được hỗ trợ."""
    return list(SUPPORTED_LANGUAGES.values())
