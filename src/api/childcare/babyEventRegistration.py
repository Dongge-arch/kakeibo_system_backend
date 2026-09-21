"""育児記録登録 API。"""

from src.api.childcare.babyBase import BabyBase


class BabyEventRegistration(BabyBase):
    """授乳、おむつ、体温などの記録を登録する。"""

    def main(self, request_dict):
        """
        処理概要: 赤ちゃんの育児記録を新規登録する。
        処理内容:
          1. ユーザーと赤ちゃんへのアクセス権を確認する。
          2. 記録内容を検証して保存する。
          3. 記録 ID を返す。

        Args:
            request_dict (dict): 育児記録を含むリクエスト。

        Returns:
            dict: 登録結果の API レスポンス。
        """
        user_id, baby, error = self.authorized_event_request(request_dict)
        if error:
            return error
        return self.save_event(user_id, baby, (request_dict.get("body") or {}).get("event") or {})
