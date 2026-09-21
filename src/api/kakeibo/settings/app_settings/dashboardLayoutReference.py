"""ダッシュボード配置参照 API。"""

from src.api.kakeibo.settings.app_settings.appSettingsBase import AppSettingsBase
from src.common.functions.response import response


class DashboardLayoutReference(AppSettingsBase):
    """ユーザーのダッシュボード配置を取得する。"""

    def main(self, request_dict):
        """
        処理概要: ダッシュボード配置を参照する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 保存済みの配置を読み取る。
          3. 配置を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: ダッシュボード配置の API レスポンス。
        """
        return response(200, self.get_dashboard_layout(self.require_user_id(request_dict)))
