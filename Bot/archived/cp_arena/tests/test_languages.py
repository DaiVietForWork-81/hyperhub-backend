# Unit tests for all supported programming languages (Top 5 Priority, 5 Secondary, Extended, and Niche Algorithmic).
import unittest

from judge.languages import (
    NICHE_ALGORITHMIC_LANGUAGES,
    SECONDARY_LANGUAGES,
    SUPPORTED_LANGUAGES,
    TOP_PRIORITY_LANGUAGES,
    get_language_by_alias,
)
from services.judge import get_sample_solution_template
from services.problem_fetcher import ProblemData


class TestLanguages(unittest.TestCase):

    def test_all_languages_present(self):
        expected_ids = [
            "cpp17",
            "cpp20",
            "cpp23",
            "python3",
            "pypy3",
            "java",
            "c",
            "csharp",
            "kotlin",
            "rust",
            "go",
            "pascal",
            "lua",
            "javascript",
            "swift",
            "ruby",
            "d",
            "scala",
            "haskell",
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
        for lang_id in expected_ids:
            self.assertIn(lang_id, SUPPORTED_LANGUAGES, f"Missing language: {lang_id}")

    def test_top_5_priority_languages(self):
        top_cats = {lang.category for lang in TOP_PRIORITY_LANGUAGES}
        expected_top_5 = {"C++", "Python", "PyPy", "Java", "C"}
        self.assertEqual(top_cats, expected_top_5)

    def test_secondary_languages(self):
        secondary_ids = {lang.id for lang in SECONDARY_LANGUAGES}
        expected_secondary = {"csharp", "kotlin", "rust", "go", "pascal"}
        self.assertEqual(secondary_ids, expected_secondary)

    def test_niche_algorithmic_languages(self):
        niche_ids = {lang.id for lang in NICHE_ALGORITHMIC_LANGUAGES}
        expected_niche = {
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
        }
        self.assertEqual(niche_ids, expected_niche)

    def test_language_alias_resolutions(self):
        cases = [
            ("cpp", "cpp17"),
            ("C++", "cpp17"),
            ("cpp17", "cpp17"),
            ("gnu++17", "cpp17"),
            ("cpp20", "cpp20"),
            ("c++20", "cpp20"),
            ("cpp23", "cpp23"),
            ("c++23", "cpp23"),
            ("python", "python3"),
            ("py", "python3"),
            ("python3", "python3"),
            ("cpython", "python3"),
            ("pypy", "pypy3"),
            ("pypy3", "pypy3"),
            ("java", "java"),
            ("java17", "java"),
            ("java21", "java"),
            ("c", "c"),
            ("gcc", "c"),
            ("c17", "c"),
            ("c#", "csharp"),
            ("cs", "csharp"),
            ("csharp", "csharp"),
            ("dotnet", "csharp"),
            ("kotlin", "kotlin"),
            ("kt", "kotlin"),
            ("rust", "rust"),
            ("rs", "rust"),
            ("go", "go"),
            ("golang", "go"),
            ("pascal", "pascal"),
            ("fpc", "pascal"),
            ("lua", "lua"),
            ("luajit", "lua"),
            ("lua5.4", "lua"),
            ("ocaml", "ocaml"),
            ("ml", "ocaml"),
            ("nim", "nim"),
            ("zig", "zig"),
            ("julia", "julia"),
            ("jl", "julia"),
            ("ts", "typescript"),
            ("typescript", "typescript"),
            ("fortran", "fortran"),
            ("f90", "fortran"),
            ("ada", "ada"),
            ("gnat", "ada"),
            ("php", "php"),
            ("perl", "perl"),
            ("racket", "racket"),
            ("elixir", "elixir"),
            ("js", "javascript"),
            ("node", "javascript"),
            ("swift", "swift"),
            ("ruby", "ruby"),
            ("rb", "ruby"),
            ("d", "d"),
            ("dmd", "d"),
            ("scala", "scala"),
            ("haskell", "haskell"),
            ("hs", "haskell"),
            ("ghc", "haskell"),
        ]
        for alias, expected_id in cases:
            lang = get_language_by_alias(alias)
            self.assertIsNotNone(lang, f"Failed to resolve alias: {alias}")
            assert lang is not None
            self.assertEqual(
                lang.id,
                expected_id,
                f"Alias {alias} resolved to {lang.id}, expected {expected_id}",
            )

    def test_sample_template_generation_for_languages(self):
        problem = ProblemData(
            id="4A",
            contest_id=4,
            index="A",
            name="Watermelon",
            rating=800,
            time_limit=1.0,
            memory_limit=64,
            samples=[("8\n", "YES\n")],
            min_rank_required="T8",
        )
        test_langs = [
            "cpp17",
            "python3",
            "pypy3",
            "java",
            "c",
            "csharp",
            "kotlin",
            "rust",
            "go",
            "pascal",
            "lua",
            "ocaml",
            "nim",
            "zig",
            "julia",
            "typescript",
            "fortran",
            "javascript",
        ]
        for lang_id in test_langs:
            tpl = get_sample_solution_template(problem, lang_id)
            self.assertIn("4A - Watermelon", tpl)
            self.assertTrue(len(tpl) > 50)


if __name__ == "__main__":
    unittest.main()
