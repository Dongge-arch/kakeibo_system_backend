# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""育児記録を共有する家族スペースのAPI。"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from src.common.functions.response import response
from src.common.base import BaseRestApi


class FamilyBase(BaseRestApi):
    """家族の作成、招待、参加、メンバー管理の共通処理。"""

    def __init__(self, db_path=None):
        """
        家族APIを初期化する。

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

    def list_families(self, user_id):
        """
        所属する家族とメンバーを取得する。

        Args:
            user_id (str): ログインユーザーID。

        Returns:
            list[dict]: 家族情報の一覧。
        """
        families = self.database.select(
            self.database.read_sql("SELECT_FAMILY_SPACE", location=__file__), {"USER_ID": user_id},
        )
        result = []
        for family in families:
            members = self.database.select(
                self.database.read_sql("SELECT_FAMILY_MEMBER_03", location=__file__),
                {"FAMILY_ID": family["FAMILY_ID"]},
            )
            result.append({"familyId": family["FAMILY_ID"], "name": family["NAME"],
                           "ownerUserId": family["OWNER_USER_ID"],
                           "members": [{"userId": row["USER_ID"], "role": row["ROLE"],
                                        "name": row.get("NICKNAME") or row.get("USER_NAME")}
                                       for row in members]})
        return result

    def create_family(self, user_id, body):
        """
        家族スペースを作成し、本人を管理者として登録する。

        Args:
            user_id (str): ログインユーザーID。
            body (dict): 家族名を含むリクエスト。

        Returns:
            dict: 作成した家族ID。
        """
        name = str(body.get("name") or "").strip()[:80]
        if not name:
            return response(400, {"errorMessage": "家族名を入力してください。"})
        family_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        self.database.insert(
            self.database.read_sql("INSERT_FAMILY_SPACE", location=__file__),
            {"FAMILY_ID": family_id, "NAME": name, "OWNER_USER_ID": user_id, "CREATED_AT": now},
        )
        self.database.insert(
            self.database.read_sql("INSERT_FAMILY_MEMBER", location=__file__),
            {"FAMILY_ID": family_id, "USER_ID": user_id, "JOINED_AT": now},
        )
        return response(201, {"familyId": family_id})

    def create_invite(self, user_id, family_id):
        """
        管理者だけが使える24時間有効の一回限りの招待コードを発行する。

        Args:
            user_id (str): ログインユーザーID。
            family_id (str): 招待先の家族ID。

        Returns:
            dict: 招待コードと有効期限。
        """
        owner = self.database.select(
            self.database.read_sql("SELECT_FAMILY_SPACE_02", location=__file__),
            {"FAMILY_ID": family_id, "OWNER_USER_ID": user_id},
        )
        if not owner:
            return response(403, {"errorMessage": "管理者のみ招待できます。"})
        code = secrets.token_urlsafe(18)
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        self.database.insert(
            self.database.read_sql("INSERT_FAMILY_INVITE", location=__file__),
            {"INVITE_ID": uuid.uuid4().hex, "FAMILY_ID": family_id,
             "CODE_HASH": hashlib.sha256(code.encode()).hexdigest(), "EXPIRES_AT": expires},
        )
        return response(201, {"code": code, "expiresAt": expires})

    def join_family(self, user_id, raw_code):
        """
        有効な招待コードを消費し、現在のユーザーを家族へ追加する。

        Args:
            user_id (str): ログインユーザーID。
            raw_code (str): 招待コード。

        Returns:
            dict: 参加した家族ID。
        """
        code = str(raw_code or "").strip()
        if not code:
            return response(400, {"errorMessage": "招待コードを入力してください。"})
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        rows = self.database.select(
            self.database.read_sql("SELECT_FAMILY_INVITE", location=__file__),
            {"CODE_HASH": code_hash},
        )
        if not rows:
            return response(404, {"errorMessage": "招待コードが無効か期限切れです。"})
        family_id = rows[0]["FAMILY_ID"]
        existing = self.database.select(
            self.database.read_sql("SELECT_FAMILY_MEMBER_02", location=__file__),
            {"FAMILY_ID": family_id, "USER_ID": user_id},
        )
        if existing:
            return response(200, {"familyId": family_id})
        used = self.database.execute(self.database.read_sql("DELETE_FAMILY_INVITE", location=__file__), {"CODE_HASH": code_hash})
        if not used:
            return response(409, {"errorMessage": "招待コードは使用済みです。"})
        self.database.insert(
            self.database.read_sql("INSERT_FAMILY_MEMBER_02", location=__file__),
            {"FAMILY_ID": family_id, "USER_ID": user_id,
             "JOINED_AT": datetime.now(timezone.utc).isoformat()},
        )
        return response(200, {"familyId": family_id})

    def remove_member(self, user_id, family_id, target_user_id):
        """
        管理者が家族メンバーの共有権限を取り消す。

        Args:
            user_id (str): ログインユーザーID。
            family_id (str): 家族ID。
            target_user_id (str): 解除対象ユーザーID。

        Returns:
            dict: 解除結果。
        """
        owner = self.database.select(
            self.database.read_sql("SELECT_FAMILY_SPACE_03", location=__file__),
            {"FAMILY_ID": family_id, "OWNER_USER_ID": user_id},
        )
        if not owner or target_user_id == user_id:
            return response(403, {"errorMessage": "このメンバーは解除できません。"})
        changed = self.database.execute(
            self.database.read_sql("DELETE_FAMILY_MEMBER", location=__file__),
            {"FAMILY_ID": family_id, "USER_ID": target_user_id},
        )
        return response(200, {"ok": bool(changed)})
