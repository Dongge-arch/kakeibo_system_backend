import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import patch


class FakeS3Client:
    def __init__(self, raise_on_head=False):
        self.head_calls = []
        self.generate_calls = []
        self.raise_on_head = raise_on_head

    def head_object(self, **kwargs):
        self.head_calls.append(kwargs)
        if self.raise_on_head:
            raise RuntimeError("S3 unavailable")

    def generate_presigned_url(self, operation_name, Params, ExpiresIn):
        self.generate_calls.append({
            "operation_name": operation_name,
            "Params": Params,
            "ExpiresIn": ExpiresIn,
        })
        return "https://example.com/presigned-url"


class SupplierLogoStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module_path = os.path.join(os.getcwd(), "src", "api", "receipt", "supplierLogoStorage.py")
        spec = importlib.util.spec_from_file_location("supplier_logo_storage_module", module_path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_url_for_accepts_generated_invoice_numbers(self):
        fake_boto3 = types.ModuleType("boto3")
        fake_client = FakeS3Client()
        fake_boto3.client = lambda service_name: fake_client

        with patch.dict(sys.modules, {"boto3": fake_boto3}):
            with patch.object(self.module, "APP_CONFIG", {"storage": {
                "supplier_logo_bucket": "test-bucket",
                "supplier_logo_prefix": "supplier-logos",
                "supplier_logo_url_expires": 3600,
            }}):
                storage = self.module.SupplierLogoStorage()
                result = storage.url_for("A12345678901234")

        self.assertEqual(result, "https://example.com/presigned-url")
        self.assertEqual(fake_client.head_calls, [{
            "Bucket": "test-bucket",
            "Key": "supplier-logos/A12345678901234",
        }])
        self.assertEqual(fake_client.generate_calls, [{
            "operation_name": "get_object",
            "Params": {
                "Bucket": "test-bucket",
                "Key": "supplier-logos/A12345678901234",
            },
            "ExpiresIn": 3600,
        }])

    def test_url_for_logs_when_s3_lookup_fails(self):
        fake_boto3 = types.ModuleType("boto3")
        fake_client = FakeS3Client(raise_on_head=True)
        fake_boto3.client = lambda service_name: fake_client

        with patch.dict(sys.modules, {"boto3": fake_boto3}):
            with patch.object(self.module, "APP_CONFIG", {"storage": {
                "supplier_logo_bucket": "test-bucket",
                "supplier_logo_prefix": "supplier-logos",
                "supplier_logo_url_expires": 3600,
            }}):
                storage = self.module.SupplierLogoStorage()
                with patch.object(self.module.log, "exception") as log_exception:
                    result = storage.url_for("T12345678901234")

        self.assertEqual(result, "")
        self.assertEqual(log_exception.call_count, 1)

    def test_upload_logs_remote_url_skip(self):
        fake_boto3 = types.ModuleType("boto3")
        fake_client = FakeS3Client()
        fake_boto3.client = lambda service_name: fake_client

        with patch.dict(sys.modules, {"boto3": fake_boto3}):
            with patch.object(self.module, "APP_CONFIG", {"storage": {
                "supplier_logo_bucket": "test-bucket",
                "supplier_logo_prefix": "supplier-logos",
                "supplier_logo_url_expires": 3600,
            }}):
                storage = self.module.SupplierLogoStorage()
                with patch.object(self.module.log, "warning") as log_warning:
                    result = storage.upload("T12345678901234", "https://example.com/logo.png")

        self.assertEqual(result, "")
        self.assertEqual(log_warning.call_count, 1)
        self.assertEqual(log_warning.call_args.args[0], "Skipped supplier logo upload for remote URL image for invoice %s.")
        self.assertEqual(log_warning.call_args.args[1], "T12345678901234")


if __name__ == "__main__":
    unittest.main()
