# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""AWSから引き継いだ外部サイト連携ジョブをArmbianで処理する。"""

from __future__ import annotations

import argparse
import json
import sys

from playwright.sync_api import sync_playwright

from src.api.kakeibo.expense_source.expenseSourceBase import ExpenseSourceBase
from src.batch.kakeibo.auto_input_targets.auto_input_financial.autoInput_Financial import (
    AutoInput_Financial,
    FINANCIAL_SERVICES,
)
from src.common.api_utils import now_ymd_hms


class ServerJobRunner(ExpenseSourceBase):
    """共有DBのPENDINGジョブを取得し、Chromiumでログインと履歴取得を行う。"""

    def main(self, request_dict):
        """共通基底の実行契約からキュー処理を呼び出す。"""
        return self.run(limit=int((request_dict.get("body") or {}).get("limit") or 10))

    def run(self, limit=10):
        jobs = self.database.select(
            """SELECT * FROM AUTO_LINKAGE_SERVER_JOB
               WHERE STATUS='PENDING' AND DEL_FLAG=0 ORDER BY ID LIMIT %(limit)s""",
            {"limit": limit},
        )
        results = []
        for job in jobs:
            results.append(self.run_job(job))
        return {"processed": len(results), "results": results}

    def run_job(self, job):
        job_id = int(self.value(job, "ID", "id"))
        connection_type = str(self.value(job, "CONNECTION_TYPE", "connection_type") or "")
        user_id = str(self.value(job, "CRE_USER_ID", "cre_user_id") or "")
        if connection_type not in FINANCIAL_SERVICES:
            return self.finish(job_id, "FAILED", {}, "Server未対応の連携種別です。")
        self.set_status(job_id, "RUNNING")
        try:
            request_data = json.loads(self.value(job, "REQUEST_JSON", "request_json") or "{}")
            previous = json.loads(self.value(job, "RESULT_JSON", "result_json") or "{}")
            result = self.browser_import(connection_type, user_id, request_data, previous, job_id)
            status = str(result.get("status") or "COMPLETED")
            return self.finish(job_id, status, result, "")
        except Exception as exc:
            return self.finish(job_id, "FAILED", {}, str(exc))

    def browser_import(self, connection_type, user_id, request_data, previous, job_id):
        connector = AutoInput_Financial(connection_type)
        config = connector.get_config(user_id)
        account_id = str(connector.value(config, "LOGIN_ID_1", "login_id_1") or "")
        password = str(connector.value(config, "LOGIN_PW_1", "login_pw_1") or "")
        verification_code = str(request_data.get("verificationCode") or request_data.get("captcha") or "").strip()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
            context_options = {"locale": "ja-JP", "timezone_id": "Asia/Tokyo"}
            if previous.get("storageState"):
                context_options["storage_state"] = previous["storageState"]
            context = browser.new_context(**context_options)
            page = context.new_page()
            if previous.get("challengeUrl") and verification_code:
                page.goto(previous["challengeUrl"], wait_until="domcontentloaded", timeout=60000)
                code_input = page.locator("input[autocomplete=one-time-code], input[name*=otp i], input[name*=code i], input[id*=code i]").first
                code_input.fill(verification_code)
                self.click_submit(page)
            else:
                page.goto(connector.login_url(config), wait_until="domcontentloaded", timeout=60000)
                login_input = page.locator("input[type=email], input[name*=mail i], input[name*=login i], input[name*=user i], input[type=text]").first
                password_input = page.locator("input[type=password]").first
                login_input.fill(account_id)
                if password_input.count():
                    password_input.fill(password)
                    self.click_submit(page)
                else:
                    # 2026-11-11 Codex: account入力とpassword入力が別ページのサイトも同じServerフローで進める。
                    self.click_submit(page)
                    page.wait_for_timeout(1000)
                    password_input = page.locator("input[type=password]").first
                    if not password_input.count():
                        raise RuntimeError("パスワード入力画面を確認できませんでした。")
                    password_input.fill(password)
                    self.click_submit(page)

            page.wait_for_timeout(1500)
            otp = page.locator("input[autocomplete=one-time-code], input[name*=otp i], input[name*=code i], input[id*=code i]")
            if otp.count() and not verification_code:
                return {
                    "ok": True,
                    "status": "OTP_REQUIRED",
                    "challengeId": str(job_id),
                    "verificationLabel": f"{FINANCIAL_SERVICES[connection_type].display_name}確認コード",
                    "expiresInSeconds": 600,
                    "message": "確認コードを入力してください。",
                    "challengeUrl": page.url,
                    "storageState": context.storage_state(),
                }

            page.goto(connector.history_url(config), wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            html = page.content()
            result = connector.complete_import(html, user_id)
            browser.close()
            return result

    @staticmethod
    def click_submit(page):
        button = page.locator("button[type=submit], input[type=submit]").first
        if button.count():
            button.click()
        else:
            page.keyboard.press("Enter")

    def set_status(self, job_id, status):
        ymd, hms = now_ymd_hms()
        self.database.update(
            """UPDATE AUTO_LINKAGE_SERVER_JOB SET STATUS=%(status)s,
                   UPD_PROG='ServerJobRunner', UPD_DT=%(ymd)s, UPD_TM=%(hms)s
               WHERE ID=%(job_id)s AND DEL_FLAG=0""",
            {"status": status, "ymd": ymd, "hms": hms, "job_id": job_id},
        )
        self.database.commit()

    def finish(self, job_id, status, result, error):
        ymd, hms = now_ymd_hms()
        self.database.update(
            """UPDATE AUTO_LINKAGE_SERVER_JOB SET STATUS=%(status)s,
                   RESULT_JSON=%(result_json)s, ERROR_MESSAGE=%(error)s,
                   UPD_PROG='ServerJobRunner', UPD_DT=%(ymd)s, UPD_TM=%(hms)s
               WHERE ID=%(job_id)s AND DEL_FLAG=0""",
            {"status": status, "result_json": json.dumps(result, ensure_ascii=False),
             "error": error[:1000], "ymd": ymd, "hms": hms, "job_id": job_id},
        )
        self.database.commit()
        return {"jobId": job_id, "status": status, "error": error[:200]}

    @staticmethod
    def value(row, *keys):
        lower = {str(key).lower(): item for key, item in (row or {}).items()}
        for key in keys:
            if key in (row or {}):
                return row.get(key)
            if str(key).lower() in lower:
                return lower[str(key).lower()]
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(ServerJobRunner().run(limit=max(1, min(args.limit, 50))), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
