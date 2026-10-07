"""
Unit tests for utils/bootstrap.py pre-flight bootstrapper.
"""

import os
import pytest
from utils.bootstrap import (
    _is_module_installed,
    check_filesystem_and_env,
    check_nodejs_environment,
    check_and_build_cpp_engine,
    run_preflight_checks,
    PROJECT_DIR,
)


def test_is_module_installed():
    assert _is_module_installed("os") is True
    assert _is_module_installed("sys") is True
    assert _is_module_installed("non_existent_module_99999_xyz") is False


def test_check_filesystem_and_env():
    check_filesystem_and_env()
    for folder in ["data", "logs", "models", "backups"]:
        folder_path = os.path.join(PROJECT_DIR, folder)
        assert os.path.isdir(folder_path)


def test_check_nodejs_environment():
    # Phải chạy mượt mà không raise exception bất kể có Node.js hay không
    check_nodejs_environment()


def test_check_and_build_cpp_engine():
    # Phải chạy mượt mà không raise exception
    check_and_build_cpp_engine()


def test_run_preflight_checks():
    # Thực thi toàn bộ chu trình preflight
    run_preflight_checks()
