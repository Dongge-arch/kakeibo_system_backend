# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import os
from typing import Optional

from src.common.config import APP_CONFIG
from src.common.database.postgresql import Postgresql


def create_database(db_path: Optional[str] = None):
    """PostgreSQLアダプターを作成する。db_pathは旧呼び出し互換のため未使用。"""
    _ = db_path
    database_config = APP_CONFIG.get("database", {}) or {}
    cloud_config = database_config.get("cloud", {}) or {}
    
    database_url = os.environ.get("KAKEIBO_DATABASE_URL") or cloud_config.get("url") or ""
    if not database_url:
        raise ValueError("KAKEIBO_DATABASE_URL is required for PostgreSQL.")

    initialize_env = os.environ.get("KAKEIBO_DATABASE_INITIALIZE")
    if initialize_env is None:
        initialize_schema = bool(cloud_config.get("initialize_schema", True))
    else:
        initialize_schema = initialize_env.lower() in ("1", "true", "yes", "on")

    return Postgresql(
        database_url=database_url,
        initialize_schema=initialize_schema,
    )
