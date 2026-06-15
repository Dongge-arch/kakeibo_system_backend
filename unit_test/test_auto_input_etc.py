from pathlib import Path

from bs4 import BeautifulSoup

from src.batch.autu_input_targets.auto_input_etc.autoInput_Etc import AutoInput_Etc


def test_parse_saved_etc_history():
    html_path = next(
        path
        for path in (Path.home() / "Desktop").glob("*.html")
        if path.stat().st_size == 51091
    )
    html = html_path.read_bytes()
    batch = AutoInput_Etc.__new__(AutoInput_Etc)

    rows = batch.parse_history(BeautifulSoup(html, "html.parser"))

    assert len(rows) == 10
    assert rows[0]["sourceKey"].startswith("ETC:")
    assert rows[0]["amount"] > 0
    assert rows[0]["exitDate"] == "2026-06-01"


def test_convert_etc_history_to_receipt():
    row = {
        "sourceKey": "ETC:test",
        "entryDate": "2026-06-01",
        "entryTime": "11:43",
        "entryPlace": "入口",
        "exitDate": "2026-06-01",
        "exitTime": "11:48",
        "exitPlace": "出口",
        "amount": 350,
        "note": "",
    }

    receipt = AutoInput_Etc.to_receipt_info("2026-06-01", [row])

    assert receipt["invoiceRegistrationNumber"] == "T9010001095716"
    assert receipt["supplierName"] == "東日本高速道路株式会社"
    assert receipt["totalPrice"] == 350
    assert receipt["receiptDetails"][0]["itemName"] == "ETC高速道路料金 11:43 入口 → 11:48 出口"
    assert receipt["receiptDetails"][0]["category1"] == "交通"
    assert receipt["receiptDetails"][0]["category2"] == "高速道路"


def test_group_etc_rows_by_date():
    rows = [
        {"exitDate": "2026-06-02", "exitTime": "12:00", "sourceKey": "2"},
        {"exitDate": "2026-06-01", "exitTime": "18:00", "sourceKey": "1b"},
        {"exitDate": "2026-06-01", "exitTime": "09:00", "sourceKey": "1a"},
    ]

    grouped = AutoInput_Etc.group_rows_by_date(rows)

    assert list(grouped) == ["2026-06-01", "2026-06-02"]
    assert [row["sourceKey"] for row in grouped["2026-06-01"]] == ["1a", "1b"]


def test_extract_saved_etc_page_urls():
    html_path = next(
        path
        for path in (Path.home() / "Desktop").glob("*.html")
        if path.stat().st_size == 51091
    )
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")

    urls = AutoInput_Etc.extract_page_urls(
        soup,
        "https://www2.etc-meisai.jp/etc/R?funccode=1013000000&nextfunc=1013000000",
    )

    assert isinstance(urls, list)
