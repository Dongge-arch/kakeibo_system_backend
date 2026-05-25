# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import logging
import logging.config
import os
from src.common.logging.formatter import DatetimeFormatter
from src.common.config import APP_CONFIG
from src.common.thread import Thread

# logging.configへ渡す前に独自formatterとログ出力先を準備する。
APP_CONFIG['logging']['formatters']['custom']['()'] = DatetimeFormatter
for handler in APP_CONFIG.get("logging", {}).get("handlers", {}).values():
    filename = handler.get("filename")
    if filename:
        log_dir = os.path.dirname(os.path.abspath(filename))
        os.makedirs(log_dir, exist_ok=True)

logging.config.dictConfig(APP_CONFIG['logging'])


class Logging():
    """ログ出力を非同期スレッドへ委譲するラッパークラス。"""

    request_id = None

    def __init__(self, class_name):
        self.logger = logging.getLogger(class_name)

    def set_request_id(self, request_id):
        """Set the request id used by log records."""
        Logging.request_id = request_id

    def reset_request_id(self):
        """ログへ付与するrequest_idを初期化する。"""
        Logging.request_id = None

    def debug(self, msg, *args, **kwargs):
        """
    Log 'msg % args' with severity 'DEBUG'.
    
    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.
    
    logger.debug("Houston, we have a %s", "thorny problem", exc_info=true)
    """
        Thread.submit(self.logger.debug,
                      msg,
                      *args,
                      **kwargs,
                      extra={"request_id": Logging.request_id})

    def info(self, msg, *args, **kwargs):
        """
    Log 'msg % args' with severity 'INFO'.
    
    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.
    
    logger.info("Houston, we have a %s", "notable problem", exc_info=true)
    """
        Thread.submit(self.logger.info,
                      msg,
                      *args,
                      **kwargs,
                      extra={"request_id": Logging.request_id})

    def warning(self, msg, *args, **kwargs):
        """
    Log 'msg % args' with severity 'WARNING'.
    
    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.
    
    logger.warning("Houston, we have a %s", "bit of a problem", exc_info=true)
    """
        Thread.submit(self.logger.warning,
                      msg,
                      *args,
                      **kwargs,
                      extra={"request_id": Logging.request_id})

    def error(self, msg, *args, **kwargs):
        """
    Log 'msg % args' with severity 'ERROR'.
    
    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.
    
    logger.error("Houston, we have a %s", "major problem", exc_info=true)
    """
        Thread.submit(self.logger.error,
                      msg,
                      *args,
                      **kwargs,
                      extra={"request_id": Logging.request_id})
