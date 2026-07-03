# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import importlib
import logging
import os
from pathlib import Path

from src.common.config import APP_CONFIG
from src.common.logging.formatter import DatetimeFormatter
from src.common.thread import Thread


def _is_aws_lambda() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("LAMBDA_TASK_ROOT"))


def _configure_local_file_handlers() -> None:
    log_dir = Path(__file__).resolve().parents[3] / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    for handler in APP_CONFIG.get("logging", {}).get("handlers", {}).values():
        filename = handler.get("filename")
        if filename:
            handler["filename"] = str(log_dir / os.path.basename(filename))
            Path(handler["filename"]).parent.mkdir(parents=True, exist_ok=True)


def _disable_lambda_file_handlers() -> None:
    # 2026-06-28 Codex: Lambdaの /var/task は読み取り専用のため、設定由来のファイルログを必ず外す。
    logging_config = APP_CONFIG.get("logging", {})
    handlers = logging_config.get("handlers", {})
    file_handlers = [
        handler_name
        for handler_name, handler in handlers.items()
        if handler.get("filename")
    ]

    for handler_name in file_handlers:
        handlers.pop(handler_name, None)

    logger_configs = [logging_config.get("root", {})] + list(logging_config.get("loggers", {}).values())
    for logger_config in logger_configs:
        logger_config["handlers"] = [
            handler_name
            for handler_name in logger_config.get("handlers", [])
            if handler_name not in file_handlers
        ]


try:
    APP_CONFIG["logging"]["formatters"]["custom"]["()"] = DatetimeFormatter
    if _is_aws_lambda():
        _disable_lambda_file_handlers()
    else:
        _configure_local_file_handlers()

    logging_config = importlib.import_module("logging.config")
    logging_config.dictConfig(APP_CONFIG["logging"])
except Exception:
    pass


class Logging:
    """Async logger wrapper used by API classes."""

    request_id = None

    def __init__(self, class_name):
        self.logger = logging.getLogger(class_name)

    def set_request_id(self, request_id):
        """Set the request id used by log records."""
        Logging.request_id = request_id

    def reset_request_id(self):
        """Reset the request id used by log records."""
        Logging.request_id = None

    def debug(self, msg, *args, **kwargs):
        Thread.submit(
            self.logger.debug,
            msg,
            *args,
            **kwargs,
            extra={"request_id": Logging.request_id},
        )

    def info(self, msg, *args, **kwargs):
        Thread.submit(
            self.logger.info,
            msg,
            *args,
            **kwargs,
            extra={"request_id": Logging.request_id},
        )

    def warning(self, msg, *args, **kwargs):
        Thread.submit(
            self.logger.warning,
            msg,
            *args,
            **kwargs,
            extra={"request_id": Logging.request_id},
        )

    def error(self, msg, *args, **kwargs):
        Thread.submit(
            self.logger.error,
            msg,
            *args,
            **kwargs,
            extra={"request_id": Logging.request_id},
        )
