# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import os
import yaml

# コンフィグファイル名
FILENAME = 'application.yaml'

# コンフィグ読み込み
APP_CONFIG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__),FILENAME),'r',encoding='utf8').read())