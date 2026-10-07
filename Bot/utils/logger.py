"""Comprehensive logging configuration with console colors and rotating file handler."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# ANSI Color codes for console output
COLORS = {
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "CRITICAL": "\033[41m\033[37m",  # White on Red
    "RESET": "\033[0m",
}


class ColoredFormatter(logging.Formatter):
    """Custom logging formatter adding colors for terminal output."""

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        original_levelname = record.levelname
        record.levelname = f"{color}{record.levelname:<8}{reset}"
        formatted = super().format(record)
        record.levelname = original_levelname
        return formatted


def setup_logger(log_level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    """Configures root logger with both rotating file output and colored console output."""
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "bot.log")

    level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if re-initialized
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = (
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) - %(message)s"
    )
    console_handler.setFormatter(
        ColoredFormatter(console_format, datefmt="%Y-%m-%d %H:%M:%S")
    )
    root_logger.addHandler(console_handler)

    # Rotating File Handler (10MB per file, 5 backup files)
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_format = (
        "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d) - %(message)s"
    )
    file_handler.setFormatter(
        logging.Formatter(file_format, datefmt="%Y-%m-%d %H:%M:%S")
    )
    root_logger.addHandler(file_handler)

    # Reduce noisy libraries
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    root_logger.info(
        f"Logger initialized with level {log_level}. Logs saved to {log_file_path}"
    )
    return root_logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Convenience getter for child loggers."""
    return logging.getLogger(name or "DiscordCPBot")
