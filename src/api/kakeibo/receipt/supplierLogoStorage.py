# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""S3 storage for supplier logos keyed by invoice registration number."""

import base64
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from src.common.api_utils import normalize_invoice_number
from src.common.config import APP_CONFIG


log = logging.getLogger(__name__)


class SupplierLogoStorage:
    _object_cache = {}
    _cache_lock = Lock()

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
        self.cache_ttl = int(os.environ.get("SUPPLIER_LOGO_CACHE_TTL", "300"))
        self.lookup_workers = max(
            1,
            min(int(os.environ.get("SUPPLIER_LOGO_LOOKUP_WORKERS", "16")), 32),
        )
        self.bulk_lookup = str(
            os.environ.get("SUPPLIER_LOGO_BULK_LOOKUP") or ""
        ).strip().lower() in {"1", "true", "yes"}

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
            self._set_cached_object(key, True)
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
        return self.urls_for([invoice_number]).get(invoice_number, "")

    def urls_for(self, invoice_numbers) -> dict:
        """
        複数のインボイス番号に対応する店舗ロゴURLをまとめて取得する。

        Args:
            invoice_numbers (Iterable[str]): インボイス登録番号の一覧。

        Returns:
            dict: インボイス登録番号をキー、署名付きURLを値とする辞書。
        """
        numbers = list(dict.fromkeys(invoice_numbers or []))
        result = {invoice_number: "" for invoice_number in numbers}
        if not self.enabled() or not numbers:
            return result

        number_to_key = {
            invoice_number: self.key_for(invoice_number)
            for invoice_number in numbers
        }
        keys = list(dict.fromkeys(key for key in number_to_key.values() if key))
        if not keys:
            return result

        now = time.monotonic()
        missing_keys = []
        existing_keys = set()
        with self._cache_lock:
            for key in keys:
                cached = self._object_cache.get((self.bucket, key))
                if cached and cached[0] > now:
                    if cached[1]:
                        existing_keys.add(key)
                else:
                    missing_keys.append(key)

        client = self._client() if missing_keys or existing_keys else None
        inaccessible_count = 0
        if missing_keys and self.bulk_lookup:
            listed_keys = self._list_existing_keys(client, set(missing_keys))
            if listed_keys is not None:
                for key in missing_keys:
                    exists = key in listed_keys
                    self._set_cached_object(key, exists)
                    if exists:
                        existing_keys.add(key)
                missing_keys = []

        if missing_keys:
            worker_count = min(self.lookup_workers, len(missing_keys))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                checks = executor.map(
                    lambda key: self._object_exists(client, key),
                    missing_keys,
                )
                for key, (exists, inaccessible) in zip(missing_keys, checks):
                    self._set_cached_object(key, exists)
                    if exists:
                        existing_keys.add(key)
                    if inaccessible:
                        inaccessible_count += 1

        if inaccessible_count:
            # 空バケットや権限制限を一件ずつ出力せず、一覧呼び出し単位で集約する。
            log.info(
                "Skipped %s supplier logos because S3 objects were not accessible.",
                inaccessible_count,
            )

        for invoice_number, key in number_to_key.items():
            if key in existing_keys:
                result[invoice_number] = self._presigned_url(client, key)
        return result

    def _list_existing_keys(self, client, requested_keys: set[str]):
        """
        指定プレフィックスのS3キーを一括取得して対象キーだけを返す。

        Args:
            client (Any): S3クライアント。
            requested_keys (set[str]): 存在確認対象のS3キー。

        Returns:
            Optional[set[str]]: 存在するキー。列挙できない場合はNone。
        """
        prefix = f"{self.prefix}/" if self.prefix else ""
        existing_keys = set()
        continuation_token = None
        try:
            while True:
                request = {"Bucket": self.bucket, "Prefix": prefix}
                if continuation_token:
                    request["ContinuationToken"] = continuation_token
                page = client.list_objects_v2(**request)
                for item in page.get("Contents") or []:
                    key = item.get("Key")
                    if key in requested_keys:
                        existing_keys.add(key)
                if existing_keys == requested_keys or not page.get("IsTruncated"):
                    return existing_keys
                continuation_token = page.get("NextContinuationToken")
                if not continuation_token:
                    return existing_keys
        except Exception as error:
            log.warning(
                "Bulk supplier logo lookup failed; falling back to object checks: %s",
                error,
            )
            return None

    def _object_exists(self, client, key: str) -> tuple[bool, bool]:
        """
        S3オブジェクトの存在を確認する。

        Args:
            client (Any): S3クライアント。
            key (str): S3オブジェクトキー。

        Returns:
            tuple[bool, bool]: 存在有無とアクセス拒否有無。
        """
        try:
            client.head_object(Bucket=self.bucket, Key=key)
            return True, False
        except Exception as error:
            if self._is_not_found_error(error):
                return False, False
            if self._is_access_denied_error(error):
                return False, True
            log.warning(
                "Skipped supplier logo because S3 URL could not be built for key %s: %s",
                key,
                error,
            )
            return False, False

    def _set_cached_object(self, key: str, exists: bool) -> None:
        """
        S3オブジェクトの存在確認結果を一定時間保持する。

        Args:
            key (str): S3オブジェクトキー。
            exists (bool): オブジェクトが存在する場合はTrue。

        Returns:
            None: 戻り値なし。
        """
        expires_at = time.monotonic() + max(self.cache_ttl, 1)
        with self._cache_lock:
            self._object_cache[(self.bucket, key)] = (expires_at, exists)

    @classmethod
    def clear_cache(cls) -> None:
        """
        店舗ロゴの存在確認キャッシュを削除する。

        Args:
            None: 引数なし。

        Returns:
            None: 戻り値なし。
        """
        with cls._cache_lock:
            cls._object_cache.clear()

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
