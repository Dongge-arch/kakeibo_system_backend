# Belc 自動登録バッチ - 設定ガイド

## 概要
このガイドでは、実際のベルク会員サイトの HTML 構造に合わせて AutoCsvInput_Belc バッチを調整する方法を説明します。

## 1. HTML 構造の確認手順

### 1.1 ブラウザの開発者ツール
1. Chrome/Firefox で Belc 会員ページ (https://cust-bf.belc.jp/mypage/PurchaseHistory) にアクセス
2. 開発者ツール (F12) を開く
3. 以下の要素を確認：

### 1.2 購入履歴一覧ページ（修正: get_all_purchase_datetimes）
チェックボックスの構造：
```html
<!-- 実際のHTMLを確認してコピーしてください -->
<input type="checkbox" name="..." value="..." />
<div class="purchase-item">
  <span class="date">2026年05月29日 11:01</span>
  <span class="store">フォルテ秦野店</span>
</div>
```

### 1.3 詳細ページの POST フォーム
開発者ツール → Network タブで、詳細ページへのPOST リクエストを確認：
```
URL: https://cust-bf.belc.jp/mypage/PurchaseHistory?handler=Detail
Form Data: 
  - __RequestVerificationToken: [CSRF token]
  - [その他の隠しフィールド]
```

## 2. コード修正手順

### 2.1 詳細ページの取得 URL と form_data 修正
ファイル: `src/batch/auto_csv_input_belc/autoCsvInput_Belc.py`
メソッド: `fetch_receipt_detail`

```python
def fetch_receipt_detail(self, session, headers, checkbox_info: dict) -> str:
    # ステップ 1: 開発者ツール Network タブで POST URL を確認
    detail_url = "https://cust-bf.belc.jp/mypage/PurchaseHistory?handler=Detail"  # ← 実際の URL に修正
    
    # ステップ 2: form_data を実際のフォーム構造に合わせて修正
    form_data = {
        checkbox_info["name"]: checkbox_info["value"],
        # "__RequestVerificationToken": ...,  # 必要に応じて追加
        # "StoreCode": ...,  # 実際のフィールドを追加
        # "Date": ...,       # 実際のフィールドを追加
    }
```

### 2.2 明細情報の抽出 セレクタ修正
メソッド: `parse_receipt_info`

**日付の抽出**:
```python
# 現在の実装:
date_input = soup.select_one("input[name='Date']")

# 実際のHTMlに合わせて修正例:
# date_input = soup.select_one("span.receipt-date")
# または
# date_input = soup.select_one(".detail-date")
```

**商品行の検出**:
```python
# 現在の実装:
for row in soup.select("tr[data-item], .receipt-detail-row"):

# 実際のHTML例（修正が必要）:
# for row in soup.select("table.item-table tbody tr"):
# または
# for row in soup.select("div.item-row"):
```

**各セレクタを確認**:
```python
item_name = row.select_one(".item-name, [data-item-name]")         # 商品名
quantity = row.select_one(".quantity, [data-quantity]")             # 数量
unit_price = row.select_one(".unit-price, [data-unit-price]")       # 単価
total_price = row.select_one(".total-price, [data-total-price]")    # 合計金額
```

### 2.3 ページネーション の max_page 取得修正
メソッド: `select_purchase_rows`

```python
# 現在の実装:
pagination = soup.select_one(".pagination, .paging, [data-max-page]")
if pagination and pagination.get("data-max-page"):
    max_page = int(pagination.get("data-max-page"))

# 実際のHTML例（修正が必要）:
# 方法1: ページボタンから取得
# page_buttons = soup.select(".pagination a")
# max_page = max([int(btn.text) for btn in page_buttons if btn.text.isdigit()])

# 方法2: 全体ページ数を表示するテキストから抽出
# page_info = soup.select_one("span.page-info")  # "1 / 5" のような形式
# if page_info:
#     max_page = int(page_info.text.split("/")[1].strip())
```

## 3. デバッグ & テスト

### 3.1 実際のHTMlを保存して確認
```python
# ファイルに保存してブラウザで開く
with open("/tmp/detail_page.html", "w") as f:
    f.write(detail_html)
```

### 3.2 BeautifulSoup で select_one をテスト
```python
from bs4 import BeautifulSoup

# HTML ファイルを読み込み
with open("/tmp/detail_page.html") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# テスト用のセレクタを実行
print("Date input:", soup.select_one("input[name='Date']"))
print("Item rows:", soup.select("tr[data-item], .receipt-detail-row"))
print("Item names:", [row.select_one(".item-name") for row in soup.select("tr")])
```

### 3.3 ログ出力の追加
デバッグのため、`parse_receipt_info` に以下を追加：
```python
self.logger.info(f"Receipt Info: {receipt_info}")
self.logger.info(f"Detail Count: {len(receipt_details)}")
```

## 4. Belc HTML 構造例

### 購入履歴一覧ページ
```html
<div class="mod-purchase-list">
  <div class="mod-purchase-list__body">
    <form method="post" action="/mypage/PurchaseHistory">
      <label>
        <input type="checkbox" name="SelectedIndexes" value="0" />
        <div class="mod-purchase-list__item">
          <span class="mod-purchase-list__title">2026年05月29日 11:01</span>
          <span class="mod-purchase-list__title-sub">フォルテ秦野店</span>
          <input type="hidden" name="StoreCode" value="001" />
          <input type="hidden" name="PosNo" value="001" />
          <input type="hidden" name="Date" value="20260529" />
          <input type="hidden" name="ReceiptNo" value="000001" />
        </div>
      </label>
    </form>
  </div>
</div>
```

### 明細ページ（参考）
```html
<div class="receipt-details">
  <h2>レシート詳細</h2>
  <table class="detail-table">
    <tbody>
      <tr data-item="001">
        <td class="item-name">商品名A</td>
        <td class="quantity">2</td>
        <td class="unit-price">100</td>
        <td class="total-price">200</td>
      </tr>
    </tbody>
  </table>
</div>
```

## 5. よくある問題

### 問題1: 日付が抽出できない
- 実際の HTML の日付フィールド名を確認してください
- `input[name='Date']` が正しいフィールドか確認

### 問題2: 商品行が検出されない
- `soup.select()` で実際のセレクタを確認
- ブラウザの開発者ツールで "Inspect Element" を使用

### 問題3: ページネーションが機能しない
- `select_purchase_rows` で max_page の計算方法を確認
- Belc のページネーション UI を直接確認

## 6. デプロイ前チェックリスト

- [ ] fetch_receipt_detail の detail_url が正しい
- [ ] fetch_receipt_detail の form_data が正しい
- [ ] parse_receipt_info のすべてのセレクタが実際の HTML と一致
- [ ] select_purchase_rows の max_page 取得ロジックが正しい
- [ ] テスト環境で少なくとも1件のレシート登録を確認
- [ ] エラーログを確認してセレクタの問題がないか検証
