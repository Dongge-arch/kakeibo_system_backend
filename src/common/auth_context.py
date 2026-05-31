# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

from contextvars import ContextVar


_current_user_id = ContextVar("current_user_id", default="")
_current_user = ContextVar("current_user", default={})
_current_request_headers = ContextVar("current_request_headers", default={})


def set_current_user_id(user_id: str):
    """現在リクエストのユーザーIDを保存する。"""
    return _current_user_id.set(user_id or "")


def reset_current_user_id(token):
    """現在リクエストのユーザーIDコンテキストを元に戻す。"""
    _current_user_id.reset(token)


def get_current_user_id() -> str:
    """現在リクエストのユーザーIDを取得する。"""
    return _current_user_id.get() or ""


def set_current_user(user: dict):
    """現在リクエストのユーザー情報を保存する。"""
    user = dict(user or {})
    user_id = user.get("userId") or user.get("user_id") or ""
    id_token = _current_user_id.set(user_id)
    user_token = _current_user.set(user)
    return id_token, user_token


def reset_current_user(tokens):
    """現在リクエストのユーザー情報コンテキストを元に戻す。"""
    id_token, user_token = tokens
    _current_user_id.reset(id_token)
    _current_user.reset(user_token)


def set_current_request_headers(headers: dict):
    """現在リクエストのHTTPヘッダーを保存する。"""
    return _current_request_headers.set(dict(headers or {}))


def reset_current_request_headers(token):
    """現在リクエストのHTTPヘッダーコンテキストを元に戻す。"""
    _current_request_headers.reset(token)


def get_current_request_headers() -> dict:
    """現在リクエストのHTTPヘッダーを取得する。"""
    return dict(_current_request_headers.get() or {})


def get_current_user() -> dict:
    """現在リクエストのユーザー情報を取得する。"""
    return dict(_current_user.get() or {})
