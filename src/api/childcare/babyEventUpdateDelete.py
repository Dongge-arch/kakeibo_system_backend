"""育児記録更新・削除 API。"""

from src.api.childcare.babyBase import BabyBase
from src.common.functions.response import response


class BabyEventUpdateDelete(BabyBase):
    """既存の育児記録を変更または削除する。"""

    def main(self, request_dict):
        """
        処理概要: 育児記録を更新または削除する。
        処理内容:
          1. ユーザーと赤ちゃんへのアクセス権を確認する。
          2. 指定された記録を変更または削除する。
          3. 処理結果を返す。

        Args:
            request_dict (dict): 操作と記録 ID を含むリクエスト。

        Returns:
            dict: 更新または削除結果の API レスポンス。
        """
        user_id, baby, error = self.authorized_event_request(request_dict)
        if error:
            return error
        body = request_dict.get("body") or {}
        if body.get("action") == "save_event":
            return self.save_event(user_id, baby, body.get("event") or {})
        if body.get("action") == "delete_event":
            return self.delete_event(baby, body.get("eventId"))
        return response(400, {"errorMessage": "unknown baby action"})
