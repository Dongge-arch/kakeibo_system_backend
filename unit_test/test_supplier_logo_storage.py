from src.api.kakeibo.receipt.supplierLogoStorage import SupplierLogoStorage


class MissingObjectError(Exception):
    def __init__(self):
        super().__init__("missing")
        self.response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }


class FakeS3Client:
    def __init__(self, existing_keys=None):
        self.existing_keys = set(existing_keys or [])
        self.head_calls = []
        self.put_calls = []
        self.list_calls = []

    def head_object(self, Bucket, Key):
        self.head_calls.append((Bucket, Key))
        if Key not in self.existing_keys:
            raise MissingObjectError()

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://logo.test/{Params['Key']}?expires={ExpiresIn}"

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        self.existing_keys.add(kwargs["Key"])

    def list_objects_v2(self, **kwargs):
        self.list_calls.append(kwargs)
        prefix = kwargs.get("Prefix") or ""
        return {
            "Contents": [
                {"Key": key}
                for key in sorted(self.existing_keys)
                if key.startswith(prefix)
            ],
            "IsTruncated": False,
        }


def build_storage(monkeypatch, client):
    monkeypatch.setenv("SUPPLIER_LOGO_S3_BUCKET", "logo-bucket")
    monkeypatch.setenv("SUPPLIER_LOGO_CACHE_TTL", "300")
    storage = SupplierLogoStorage()
    monkeypatch.setattr(storage, "_client", lambda: client)
    storage.clear_cache()
    return storage


def test_urls_for_deduplicates_and_caches_object_checks(monkeypatch):
    client = FakeS3Client({"supplier-logos/T1111111111111"})
    storage = build_storage(monkeypatch, client)

    first = storage.urls_for(["T1111111111111", "T2222222222222", "T1111111111111"])
    second = storage.urls_for(["T1111111111111", "T2222222222222"])

    assert first["T1111111111111"].startswith("https://logo.test/")
    assert first["T2222222222222"] == ""
    assert second == first
    assert len(client.head_calls) == 2


def test_upload_refreshes_cache_without_followup_head_request(monkeypatch):
    client = FakeS3Client()
    storage = build_storage(monkeypatch, client)

    storage.upload("T3333333333333", "aGVsbG8=")
    result = storage.url_for("T3333333333333")

    assert result.startswith("https://logo.test/")
    assert client.head_calls == []
    assert len(client.put_calls) == 1


def test_bulk_lookup_uses_one_list_request_for_many_invoices(monkeypatch):
    monkeypatch.setenv("SUPPLIER_LOGO_BULK_LOOKUP", "true")
    client = FakeS3Client({"supplier-logos/T1111111111111"})
    storage = build_storage(monkeypatch, client)

    result = storage.urls_for(["T1111111111111", "T2222222222222"])

    assert result["T1111111111111"].startswith("https://logo.test/")
    assert result["T2222222222222"] == ""
    assert len(client.list_calls) == 1
    assert client.head_calls == []
