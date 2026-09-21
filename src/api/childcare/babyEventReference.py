"""育児記録参照 API。"""

from src.api.childcare.babyBase import BabyBase


class BabyEventReference(BabyBase):
    """指定日の育児記録と集計を取得する。"""

    def main(self, request_dict):
        """
        処理概要: 指定日の育児記録を参照する。
        処理内容:
          1. ユーザーと赤ちゃんへのアクセス権を確認する。
          2. 記録と日次集計を取得する。
          3. 結果を返す。

        Args:
            request_dict (dict): 赤ちゃん ID と日付を含むリクエスト。

        Returns:
            dict: 記録と集計の API レスポンス。
        """
        _, baby, error = self.authorized_event_request(request_dict)
        if error:
            return error
        return self.list_events(baby, (request_dict.get("body") or {}).get("day"))
