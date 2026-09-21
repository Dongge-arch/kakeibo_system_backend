# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""赤ちゃんの基本情報と日々の記録を扱うAPI。"""

import json
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.common.functions.response import response
from src.common.base import BaseRestApi


class BabyBase(BaseRestApi):
    """家族メンバーに限った育児情報の共通処理。"""

    EVENT_TYPES = {"feed", "diaper", "temperature", "sleep", "growth", "note"}

    def __init__(self, db_path=None):
        """
        育児APIを初期化する。

        Args:
            db_path (str | None): ローカルDBファイルのパス。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path, db_schema="childcare")

    def validate_body(self, request_dict):
        """
        共通のリクエスト検証を実行する。

        Args:
            request_dict (dict): リクエスト情報。

        Returns:
            None: 戻り値なし。
        """
        return super().validate_body(request_dict)

    def authorized_event_request(self, request_dict):
        """
        記録操作に共通する家族所属と赤ちゃんへのアクセス権を確認する。

        Args:
            request_dict (dict): 赤ちゃん ID を含む認証済みリクエスト。

        Returns:
            tuple: ユーザー ID、赤ちゃん情報、またはエラーレスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return None, None, response(401, {"errorMessage": "ログインしてください。"})
        body = request_dict.get("body") or {}
        baby_id = body.get("babyId") or (body.get("event") or {}).get("babyId")
        baby = self.authorized_baby(user_id, baby_id)
        if not baby:
            return user_id, None, response(403, {"errorMessage": "赤ちゃんの記録にアクセスできません。"})
        return user_id, baby, None

    def is_member(self, user_id, family_id):
        """
        ユーザーの家族所属を確認する。

        Args:
            user_id (str): ログインユーザーID。
            family_id (str): 家族ID。

        Returns:
            bool: 所属する場合はTrue。
        """
        return bool(self.database.select(
            self.database.read_sql("SELECT_FAMILY_MEMBER", location=__file__),
            {"USER_ID": user_id, "FAMILY_ID": family_id},
        ))

    def authorized_baby(self, user_id, baby_id):
        """
        家族所属を満たす赤ちゃん情報を取得する。

        Args:
            user_id (str): ログインユーザーID。
            baby_id (str): 赤ちゃんID。

        Returns:
            dict | None: 認可された赤ちゃん情報。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_BABY_PROFILE", location=__file__),
            {"BABY_ID": baby_id, "USER_ID": user_id},
        )
        return rows[0] if rows else None

    def list_babies(self, family_id):
        """
        家族の赤ちゃん情報を一覧で返す。

        Args:
            family_id (str): 家族ID。

        Returns:
            list[dict]: 赤ちゃん情報の一覧。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_BABY_PROFILE_02", location=__file__),
            {"FAMILY_ID": family_id},
        )
        return [self.baby_from_row(row) for row in rows]

    def save_baby(self, user_id, baby):
        """
        家族の赤ちゃんの基本情報を登録または変更する。

        Args:
            user_id (str): ログインユーザーID。
            baby (dict): 名前、生年月日、メモを含む情報。

        Returns:
            dict: 保存した赤ちゃんID。
        """
        baby_id = str(baby.get("babyId") or "")
        family_id = str(baby.get("familyId") or "")
        name = str(baby.get("name") or "").strip()[:80]
        birthday = str(baby.get("birthDate") or "")
        try:
            parsed = date.fromisoformat(birthday)
        except ValueError:
            return response(400, {"errorMessage": "生年月日を確認してください。"})
        if not name or parsed > date.today():
            return response(400, {"errorMessage": "名前と生年月日を確認してください。"})
        if not self.is_member(user_id, family_id):
            return response(403, {"errorMessage": "家族へのアクセス権がありません。"})
        values = {"BABY_ID": baby_id or uuid.uuid4().hex, "FAMILY_ID": family_id,
                  "NAME": name, "BIRTH_DATE": birthday,
                  "NOTES": str(baby.get("notes") or "").strip()[:3000],
                  "UPDATED_AT": datetime.now(timezone.utc).isoformat()}
        if baby_id:
            existing = self.authorized_baby(user_id, baby_id)
            if not existing or existing["FAMILY_ID"] != family_id:
                return response(404, {"errorMessage": "赤ちゃんが見つかりません。"})
            self.database.execute(
                self.database.read_sql("UPDATE_BABY_PROFILE", location=__file__), values,
            )
        else:
            self.database.insert(
                self.database.read_sql("INSERT_BABY_PROFILE", location=__file__), values,
            )
        return response(200, {"babyId": values["BABY_ID"]})

    def delete_baby(self, user_id, baby_id):
        """
        認可された赤ちゃんとその記録を削除する。

        Args:
            user_id (str): ログインユーザーID。
            baby_id (str): 削除する赤ちゃんID。

        Returns:
            dict: 削除結果。
        """
        baby = self.authorized_baby(user_id, baby_id)
        if not baby:
            return response(403, {"errorMessage": "赤ちゃんの記録にアクセスできません。"})
        params = {"BABY_ID": baby_id, "FAMILY_ID": baby["FAMILY_ID"]}
        self.database.execute(self.database.read_sql("DELETE_BABY_EVENT", location=__file__), params)
        self.database.execute(self.database.read_sql("DELETE_BABY_PROFILE", location=__file__), params)
        return response(200, {"ok": True})

    def list_events(self, baby, day):
        """
        指定日の育児記録と日次集計を取得する。

        Args:
            baby (dict): 認可済みの赤ちゃん情報。
            day (str): YYYY-MM-DD形式の日付。

        Returns:
            dict: 時間順の記録と集計。
        """
        try:
            date.fromisoformat(str(day))
        except ValueError:
            return response(400, {"errorMessage": "日付を確認してください。"})
        rows = self.database.select(
            self.database.read_sql("SELECT_BABY_EVENT", location=__file__),
            {"BABY_ID": baby["BABY_ID"], "FAMILY_ID": baby["FAMILY_ID"],
             "HAPPENED_AT": str(day)},
        )
        events = [self.event_from_row(row) for row in rows]
        summary = {"feeds": 0, "milkMl": 0, "wet": 0, "stool": 0, "sleepMinutes": 0,
                   "temperatures": []}
        for event in events:
            data = event["data"]
            if event["type"] == "feed":
                summary["feeds"] += 1
                summary["milkMl"] += float(data.get("amountMl") or 0)
            elif event["type"] == "diaper":
                summary["wet"] += data.get("kind") in ("wet", "both")
                summary["stool"] += data.get("kind") in ("stool", "both")
            elif event["type"] == "sleep":
                summary["sleepMinutes"] += int(data.get("durationMin") or 0)
            elif event["type"] == "temperature":
                summary["temperatures"].append(data.get("temperatureC"))
        return response(200, {"events": events, "summary": summary})

    def save_event(self, user_id, baby, event):
        """
        育児記録の値と所有家族を検証して保存する。

        Args:
            user_id (str): 記録者ユーザーID。
            baby (dict): 認可済みの赤ちゃん情報。
            event (dict): 記録種別、時刻、内容。

        Returns:
            dict: 保存した記録ID。
        """
        event_type = event.get("type")
        happened_at = str(event.get("happenedAt") or "")
        data = event.get("data")
        if event_type not in self.EVENT_TYPES or not isinstance(data, dict):
            return response(400, {"errorMessage": "記録の種類を確認してください。"})
        try:
            event_time = datetime.fromisoformat(happened_at)
        except ValueError:
            return response(400, {"errorMessage": "記録日時を確認してください。"})
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
        error = self.validate_event_data(event_type, data)
        if error:
            return response(400, {"errorMessage": error})
        event_id = str(event.get("eventId") or uuid.uuid4().hex)
        values = {"EVENT_ID": event_id, "BABY_ID": baby["BABY_ID"],
                  "FAMILY_ID": baby["FAMILY_ID"], "EVENT_TYPE": event_type,
                  "HAPPENED_AT": event_time.isoformat(), "DATA_JSON": json.dumps(data, ensure_ascii=False),
                  "CREATED_BY": user_id, "CREATED_AT": datetime.now(timezone.utc).isoformat()}
        if event.get("eventId"):
            changed = self.database.execute(
                self.database.read_sql("UPDATE_BABY_EVENT", location=__file__), values,
            )
            if not changed:
                return response(404, {"errorMessage": "記録が見つかりません。"})
        else:
            self.database.insert(
                self.database.read_sql("INSERT_BABY_EVENT", location=__file__), values,
            )
        return response(200, {"eventId": event_id})

    def delete_event(self, baby, event_id):
        """
        同じ家族の育児記録を削除する。

        Args:
            baby (dict): 認可済みの赤ちゃん情報。
            event_id (str): 削除する記録ID。

        Returns:
            dict: 削除結果。
        """
        changed = self.database.execute(
            self.database.read_sql("DELETE_BABY_EVENT_02", location=__file__),
            {"EVENT_ID": event_id, "BABY_ID": baby["BABY_ID"], "FAMILY_ID": baby["FAMILY_ID"]},
        )
        return response(200 if changed else 404, {"ok": bool(changed)})

    @staticmethod
    def validate_event_data(event_type, data):
        """
        記録種別ごとの必須項目と数値範囲を検証する。

        Args:
            event_type (str): 記録種別。
            data (dict): 記録内容。

        Returns:
            str | None: エラーメッセージ。正常時はNone。
        """
        def numeric(key, minimum, maximum, required=True):
            value = data.get(key)
            if value in (None, ""):
                return not required
            try:
                return minimum <= float(value) <= maximum
            except (TypeError, ValueError):
                return False

        if event_type == "feed":
            if data.get("method") not in {"breast", "formula", "expressed"}:
                return "授乳方法を選択してください。"
            if not numeric("amountMl", 0, 2000, False) or not numeric("durationMin", 0, 300, False):
                return "授乳量または時間を確認してください。"
        if event_type == "diaper" and data.get("kind") not in {"wet", "stool", "both"}:
            return "おむつの内容を選択してください。"
        if event_type == "temperature" and not numeric("temperatureC", 25, 45):
            return "体温を確認してください。"
        if event_type == "sleep" and not numeric("durationMin", 1, 1440):
            return "睡眠時間を確認してください。"
        if event_type == "growth" and not (numeric("weightKg", 0.1, 100, False)
                                               and numeric("lengthCm", 20, 200, False)):
            return "体重または身長を確認してください。"
        if event_type == "note" and not str(data.get("text") or "").strip():
            return "メモを入力してください。"
        return None

    @staticmethod
    def baby_from_row(row):
        """
        赤ちゃんのDB行を画面用に変換する。

        Args:
            row (dict): DBの赤ちゃん行。

        Returns:
            dict: 画面用赤ちゃん情報。
        """
        return {"babyId": row["BABY_ID"], "familyId": row["FAMILY_ID"],
                "name": row["NAME"], "birthDate": str(row["BIRTH_DATE"]),
                "notes": row.get("NOTES") or ""}

    @staticmethod
    def event_from_row(row):
        """
        育児記録のDB行を画面用に変換する。

        Args:
            row (dict): DBの育児記録行。

        Returns:
            dict: 画面用育児記録。
        """
        return {"eventId": row["EVENT_ID"], "babyId": row["BABY_ID"],
                "type": row["EVENT_TYPE"], "happenedAt": row["HAPPENED_AT"].astimezone(ZoneInfo("Asia/Tokyo")).isoformat(),
                "data": json.loads(row["DATA_JSON"]), "createdBy": row["CREATED_BY"]}
