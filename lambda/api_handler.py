# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""API Gateway / Lambda Function URL から FastAPI アプリを呼び出す入口。"""

from mangum import Mangum

from backend.app import app


handler = Mangum(app)
