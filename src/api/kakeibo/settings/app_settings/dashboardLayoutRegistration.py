"""ダッシュボード配置保存 API。"""

from src.api.kakeibo.settings.app_settings.appSettingsBase import AppSettingsBase
from src.common.functions.response import response


class DashboardLayoutRegistration(AppSettingsBase):
    """ユーザーのダッシュボード配置を保存する。"""

    def main(self, request_dict):
        """
        処理概要: ダッシュボード配置を保存する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 既存設定を維持しながら配置を保存する。
          3. 保存結果を返す。

        Args:
            request_dict (dict): 配置を含む認証済みリクエスト。

        Returns:
            dict: 保存結果の API レスポンス。
        """
        user_id = self.require_user_id(request_dict)
        self.save_dashboard_layout((request_dict.get("body") or {}).get("layout") or [], user_id)
        return response(200, {"ok": True})
