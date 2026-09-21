"""バッチ処理の共通基底クラス。"""

from src.common.base.base_lambda import BaseLambda


class BaseBatch(BaseLambda):
    """スケジュール実行・自動入力が継承するクラス。"""
