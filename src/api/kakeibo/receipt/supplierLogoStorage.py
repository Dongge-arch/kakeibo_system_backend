# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""S3 storage for supplier logos keyed by invoice registration number."""

import base64
import logging
import os
import re

from src.common.api_utils import normalize_invoice_number
from src.common.config import APP_CONFIG


log = logging.getLogger(__name__)


class SupplierLogoStorage:
    def __init__(self):
        """
        クラスを初期化する。

        Args:
            None: 引数なし。

        Returns:
            None: 戻り値なし。
        """
        storage_config = APP_CONFIG.get("storage") or {}
        self.bucket = self._setting(
            "SUPPLIER_LOGO_S3_BUCKET",
            storage_config,
            "supplier_logo_bucket",
            "",
        )
        self.prefix = self._setting(
            "SUPPLIER_LOGO_S3_PREFIX",
            storage_config,
            "supplier_logo_prefix",
            "supplier-logos",
        ).strip("/")
        self.expires_in = int(
            self._setting(
                "SUPPLIER_LOGO_URL_EXPIRES",
                storage_config,
                "supplier_logo_url_expires",
                3600,
            )
        )

    def enabled(self) -> bool:
        """
        enabledの処理を実行する。

        Args:
            None: 引数なし。

        Returns:
            bool: 処理結果。
        """
        return bool(self.bucket)

    def _setting(self, env_name: str, config: dict, config_name: str, default):
        """
        _settingの処理を実行する。

        Args:
            env_name (str): env_nameの値。
            config (dict): configの値。
            config_name (str): config_nameの値。
            default (Any): defaultの値。

        Returns:
            Any: 処理結果。
        """
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value
        return config.get(config_name) or default

    def key_for(self, invoice_number: str) -> str:
        """
        key_forの処理を実行する。

        Args:
            invoice_number (str): invoice_numberの値。

        Returns:
            str: 処理結果。
        """
        invoice_number = str(invoice_number or "").strip().upper()
        if not invoice_number:
            return ""

        normalized = normalize_invoice_number(invoice_number)
        if normalized:
            invoice_number = normalized

        return f"{self.prefix}/{invoice_number}" if self.prefix else invoice_number

    def upload(self, invoice_number: str, image_value) -> str:
        """
        uploadの処理を実行する。

        Args:
            invoice_number (str): invoice_numberの値。
            image_value (Any): image_valueの値。

        Returns:
            str: 処理結果。
        """
        log.info("Uploading supplier logo for invoice %s.", invoice_number)
        key = self.key_for(invoice_number)
        if not self.enabled():
            # 2026-06-28 Codex: ロゴ未設定は通常運用でも起きるため、CloudWatchノイズを抑える。
            log.info(
                "Skipped supplier logo upload because S3 bucket is not configured for invoice %s.",
                invoice_number,
            )
            return ""
        if not key or not image_value:
            # 2026-06-28 Codex: 画像未指定はエラーではないため info に落とす。
            log.info(
                "Skipped supplier logo upload because image payload is empty for invoice %s.",
                invoice_number,
            )
            return ""

        body, content_type = self._decode_image(image_value)
        if not body:
            raw_value = str(image_value or "").strip()
            if raw_value.startswith(("http://", "https://")):
                # 2026-06-28 Codex: 既存の署名付きURLは再アップロード対象外として扱う。
                log.info(
                    "Skipped supplier logo upload for remote URL image for invoice %s.",
                    invoice_number,
                )
            else:
                log.warning(
                    "Skipped supplier logo upload because image payload could not be decoded for invoice %s.",
                    invoice_number,
                )
            return ""

        try:
            client = self._client()
            client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
            log.info(
                "Uploaded supplier logo for invoice %s to S3 key %s in bucket %s.",
                invoice_number,
                key,
                self.bucket,
            )
            return key
        except Exception:
            log.exception("Failed to upload supplier logo to S3.")
            return ""

    def url_for(self, invoice_number: str) -> str:
        """
        url_forの処理を実行する。

        Args:
            invoice_number (str): invoice_numberの値。

        Returns:
            str: 処理結果。
        """
        key = self.key_for(invoice_number)
        if not self.enabled() or not key:
            return ""

        try:
            client = self._client()
            client.head_object(Bucket=self.bucket, Key=key)
            return self._presigned_url(client, key)
        except Exception as e:
            if self._is_not_found_error(e):
                return ""
            if self._is_access_denied_error(e):
                # 2026-06-28 Codex: S3権限/既存オブジェクト問題で一覧画面全体を失敗扱いにしない。
                log.info(
                    "Skipped supplier logo because S3 object could not be accessed for key %s.",
                    key,
                )
                return ""
            log.warning(
                "Skipped supplier logo because S3 URL could not be built for key %s: %s",
                key,
                e,
            )
            return ""

    def _is_not_found_error(self, error: Exception) -> bool:
        """
        _is_not_found_errorの処理を実行する。

        Args:
            error (Exception): 発生した例外。

        Returns:
            bool: 処理結果。
        """
        response = getattr(error, "response", {}) or {}
        error_code = str((response.get("Error") or {}).get("Code") or "")
        status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return error_code in {"404", "NoSuchKey", "NotFound"} or status_code == 404

    def _is_access_denied_error(self, error: Exception) -> bool:
        """
        _is_access_denied_errorの処理を実行する。

        Args:
            error (Exception): 発生した例外。

        Returns:
            bool: 処理結果。
        """
        response = getattr(error, "response", {}) or {}
        error_code = str((response.get("Error") or {}).get("Code") or "")
        status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return error_code in {"403", "AccessDenied"} or status_code == 403

    def _presigned_url(self, client, key: str) -> str:
        """
        _presigned_urlの処理を実行する。

        Args:
            client (Any): clientの値。
            key (str): keyの値。

        Returns:
            str: 処理結果。
        """
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.expires_in,
        )

    def _client(self):
        """
        _clientの処理を実行する。

        Args:
            None: 引数なし。

        Returns:
            Any: 処理結果。
        """
        import boto3

        return boto3.client("s3")

    def _decode_image(self, image_value) -> tuple[bytes, str]:
        """
        _decode_imageの処理を実行する。

        Args:
            image_value (Any): image_valueの値。

        Returns:
            tuple[bytes, str]: 処理結果。
        """
        if isinstance(image_value, bytes):
            return image_value, "application/octet-stream"

        raw_value = str(image_value or "").strip()
        content_type = "image/png"
        if not raw_value:
            return b"", "application/octet-stream"
        if raw_value.startswith(("http://", "https://")):
            return b"", content_type

        match = re.match(r"^data:([^;,]+);base64,(.*)$", raw_value, re.DOTALL)
        if match:
            content_type = match.group(1) or content_type
            raw_value = match.group(2)

        try:
            return base64.b64decode(raw_value, validate=True), content_type
        except Exception:
            return b"", content_type
