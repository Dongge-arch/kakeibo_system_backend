# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""
filename: base_validator.py
Date: 2024-09-01
"""

from abc import abstractmethod
from src.common.base import Base
from src.common.exception import Error


class BaseValidator(Base):
    """
    リクエストボディのバリデーションチェックオブジェクトの抽象クラス。
    """

    def __init__(self, class_name):
        """
        クラスを初期化する。

        Args:
            class_name (Any): class_nameの値。

        Returns:
            None: 戻り値なし。
        """
        if not self._initialized:
            super().__init__(class_name)
            self._initialized = True

    def __call__(self, **kwargs):
        """
        __call__の処理を実行する。

        Args:
            **kwargs: 追加のキーワード引数。

        Returns:
            Any: 処理結果。
        """
        self.call(**kwargs)

    def call(self, **kwargs) -> dict:
        """
        チェックを行うメソッド

        Args:
            **kwargs: 追加のキーワード引数。

        Returns:
            dict: 処理結果。
        """
        try:
            self.main(**kwargs)
        except Error as e:
            raise e
        except Exception as e:
            raise self.exception(e)

    @abstractmethod
    def main(self, **kwargs) -> dict:
        """
        処理概要: バリデーションの主処理を定義する。
        処理内容:
          1. 入力値を受け取る。
          2. 実装クラスで検証する。
          3. 検証結果を返す。

        Args:
            **kwargs: チェックパラメータ

        Returns:
            dict: 処理結果。

        Raises:
            Error: チェックエラーがある場合の例外。エラーコードを返す。
        """
        pass

    def exception(self, e: Exception) -> None:
        """
        チェック中に例外が発生した場合の処理を行うメソッド

        Args:
            e (Exception): 例外

        Returns:
            dict: REST APIのレスポンスとしてエラーコードを返す
        """
        if isinstance(e, Error):
            self.logger.info(e)
            raise e
        else:
            self.logger.error(e)
            import traceback
            traceback.print_exc()
            raise Error(510, "1000062")
