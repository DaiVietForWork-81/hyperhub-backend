"""Judge engine package for compiling, isolating, and executing user code in sandboxes."""

from judge.checker import CheckResult, OutputChecker
from judge.languages import SUPPORTED_LANGUAGES, LanguageConfig, get_language_by_alias
from judge.sandbox import CodeSandbox, ExecutionResult
from judge.static_analyzer import StaticComplexityAnalyzer

__all__ = [
    "SUPPORTED_LANGUAGES",
    "CheckResult",
    "CodeSandbox",
    "ExecutionResult",
    "LanguageConfig",
    "OutputChecker",
    "StaticComplexityAnalyzer",
    "get_language_by_alias",
]
