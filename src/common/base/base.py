# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""全クラス共通の基底クラスを定義する。"""

import os
import sys
from abc import ABC

# 直接実行時のモジュール解決エラー対策
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.common.logging import Logging


class Singleton(ABC):
    """継承クラスをプロセス内で単一インスタンスとして扱う基底クラス。"""

    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance


class Base(Singleton):
    """全クラス共通の基底クラス。"""

    def __init__(self, class_name):
        self.logger = Logging(class_name)
        self._initialized = True
