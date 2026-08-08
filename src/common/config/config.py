# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import os
import yaml

# コンフィグファイル名
FILENAME = 'application.yaml'

# コンフィグ読み込み
APP_CONFIG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__),FILENAME),'r',encoding='utf8').read())


def _set_if_env(config_path, env_name):
    """環境変数が設定されている場合だけ、application.yamlの値を上書きする。"""
    env_value = os.environ.get(env_name)
    if env_value is None:
        return
    current = APP_CONFIG
    for key in config_path[:-1]:
        current = current.setdefault(key, {})
    current[config_path[-1]] = env_value


# 2026-07-15 Codex: Armbianサーバー配置時に設定ファイルへ秘密情報を書かずに済むよう、主要設定を環境変数で上書き可能にする。
_set_if_env(("ai_receipt", "gemini_api_key"), "GEMINI_API_KEY")
_set_if_env(("ai_receipt", "gemini_model"), "GEMINI_MODEL")
_set_if_env(("api", "key"), "KAKEIBO_API_KEY")
