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
        """
        if not self._initialized:
            super().__init__(class_name)
            self._initialized = True

    def __call__(self, **kwargs):
        self.call(**kwargs)

    def call(self, **kwargs) -> dict:
        """
        チェックを行うメソッド
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
        チェック定義

        Args:
            **kwargs: チェックパラメータ

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
