# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""S3 storage for supplier logos keyed by invoice registration number."""

import base64
import logging
import os
import re

from src.common.config import APP_CONFIG


log = logging.getLogger(__name__)


class SupplierLogoStorage:
    def __init__(self):
        storage_config = APP_CONFIG.get("storage") or {}
        self.bucket = (
            os.environ.get("SUPPLIER_LOGO_S3_BUCKET")
            or storage_config.get("supplier_logo_bucket")
            or ""
        )
        self.prefix = (
            os.environ.get("SUPPLIER_LOGO_S3_PREFIX")
            or storage_config.get("supplier_logo_prefix")
            or "supplier-logos"
        ).strip("/")
        self.expires_in = int(
            os.environ.get("SUPPLIER_LOGO_URL_EXPIRES")
            or storage_config.get("supplier_logo_url_expires")
            or 3600
        )

    def enabled(self) -> bool:
        return bool(self.bucket)

    def key_for(self, invoice_number: str) -> str:
        invoice_number = str(invoice_number or "").strip().upper()
        if not invoice_number.startswith("T"):
            return ""
        return f"{self.prefix}/{invoice_number}" if self.prefix else invoice_number

    def upload(self, invoice_number: str, image_value) -> str:
        key = self.key_for(invoice_number)
        if not self.enabled() or not key or not image_value:
            return ""

        body, content_type = self._decode_image(image_value)
        if not body:
            return ""

        try:
            client = self._client()
            client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
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
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=self.expires_in,
            )
        except Exception:
            return ""

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
