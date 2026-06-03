# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""S3 storage for supplier logos keyed by invoice registration number."""

import base64
import logging
import os
import re

from src.api.utils import normalize_invoice_number
from src.common.config import APP_CONFIG


log = logging.getLogger(__name__)


class SupplierLogoStorage:
    def __init__(self):
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
        return bool(self.bucket)

    def _setting(self, env_name: str, config: dict, config_name: str, default):
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value
        return config.get(config_name) or default

    def key_for(self, invoice_number: str) -> str:
        invoice_number = str(invoice_number or "").strip().upper()
        if not invoice_number:
            return ""

        normalized = normalize_invoice_number(invoice_number)
        if normalized:
            invoice_number = normalized

        return f"{self.prefix}/{invoice_number}" if self.prefix else invoice_number

    def upload(self, invoice_number: str, image_value) -> str:
        log.info("Uploading supplier logo for invoice %s.", invoice_number)
        key = self.key_for(invoice_number)
        if not self.enabled():
            log.warning(
                "Skipped supplier logo upload because S3 bucket is not configured for invoice %s.",
                invoice_number,
            )
            return ""
        if not key or not image_value:
            log.warning(
                "Skipped supplier logo upload because image payload is empty for invoice %s.",
                invoice_number,
            )
            return ""

        body, content_type = self._decode_image(image_value)
        if not body:
            raw_value = str(image_value or "").strip()
            if raw_value.startswith(("http://", "https://")):
                log.warning(
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
                log.warning(
                    "Could not verify supplier logo object with head_object; returning presigned URL for key %s.",
                    key,
                )
                return self._presigned_url(self._client(), key)
            log.exception("Failed to build supplier logo URL from S3.")
            return ""

    def _is_not_found_error(self, error: Exception) -> bool:
        response = getattr(error, "response", {}) or {}
        error_code = str((response.get("Error") or {}).get("Code") or "")
        status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return error_code in {"404", "NoSuchKey", "NotFound"} or status_code == 404

    def _is_access_denied_error(self, error: Exception) -> bool:
        response = getattr(error, "response", {}) or {}
        error_code = str((response.get("Error") or {}).get("Code") or "")
        status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return error_code in {"403", "AccessDenied"} or status_code == 403

    def _presigned_url(self, client, key: str) -> str:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.expires_in,
        )

    def _client(self):
        import boto3

        return boto3.client("s3")

    def _decode_image(self, image_value) -> tuple[bytes, str]:
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
