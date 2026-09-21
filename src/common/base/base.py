# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""全クラス共通の基底クラスを定義する。"""

import os
import sys
from abc import ABC, abstractmethod

from src.common.logging import Logging


class Singleton(ABC):
    """継承クラスをプロセス内で単一インスタンスとして扱う基底クラス。"""

    _initialized = False

    def __new__(cls, *args, **kwargs):
        """
        __new__の処理を実行する。

        Args:
            *args: 追加の位置引数。
            **kwargs: 追加のキーワード引数。

        Returns:
            Any: 処理結果。
        """
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance


class Base(Singleton):
    """全クラス共通の基底クラス。"""

    def __init__(self, class_name):
        """
        クラスを初期化する。

        Args:
            class_name (Any): class_nameの値。

        Returns:
            None: 戻り値なし。
        """
        self.logger = Logging(class_name)
        self._initialized = True
