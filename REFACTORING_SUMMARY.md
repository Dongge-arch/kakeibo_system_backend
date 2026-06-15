# AutoInput_Belc リファクタリング完了

## 概要
ベルク店舗の購入履歴から自動的にレシート情報を抽出し、登録するバッチクラスの設計をリファクタリングしました。

## 実装された機能

### 1. 詳細ページ取得 (`fetch_receipt_detail`)
- 選択されたチェックボックス情報に基づいて、明細ページをPOSTリクエストで取得
- セッションと認証ヘッダーを保持して、ログイン状態を維持

### 2. レシート情報解析 (`parse_receipt_info`)
- 明細ページのHTMLをBeautifulSoup4で解析
- 以下の情報を自動抽出：
  - **receiptInfo** (領収書の基本情報)
    - invoiceRegistrationNumber: レシート番号
    - supplierName: ベルク
    - receiptDate: 購入日（YYYY-MM-DD形式）
    - receiptTime: 購入時刻
    - taxFlag: 税区分
    - receiptDetailCount: 明細数
  - **receiptDetails** (購入商品の明細)
    - itemName: 商品名
    - category1/category2: カテゴリ（デフォルト: "その他"）
    - taxRate: 税率（デフォルト: 10）
    - quantity: 数量
    - unit: 単位（デフォルト: "個"）
    - unitPrice: 単価
    - discount: 割引
    - totalPrice: 合計金額

### 3. ページ検索ロジック (`select_purchase_rows`)
- 複数ページを検索して、対象日付に一致するすべてのチェックボックスを特定
- ページングロジック：最初のページから開始し、max_page まで反復
- 各ページから `find_matching_checkboxes` でマッチするアイテムを抽出

### 4. メイン処理フロー (`main`)
以下の流れでレシート登録を自動化：

1. ログイン状態でベルク購入履歴ページにアクセス
2. すべての購入日時を抽出
3. データベースから既に登録済みの日時を取得
4. 未登録の日時をフィルタリング
5. **すべてのページから** 未登録の購入記録のチェックボックスを選択
6. **各選択された記録について**：
   - 詳細ページを取得
   - 商品情報を解析
   - receiptInfo JSON に変換
   - NewReceiptRegistration API に送信して登録
7. 登録結果を返却

### 5. 統合ポイント
NewReceiptRegistration クラスとの統合：
```python
request_dict = {
    "headers": {"x-kakeibo-user-id": user_id, "Content-Type": "application/json"},
    "body": {"receiptInfo": receipt_info}
}
result = registration_api.main(request_dict)
```

## ファイル変更

### Modified: `src/batch/auto_input_belc/autoInput_Belc.py`

**新規追加メソッド**:
- `fetch_receipt_detail(session, headers, checkbox_info)`: 詳細ページ取得
- `parse_receipt_info(detail_html, user_id)`: HTML から receiptInfo に変換
- `select_purchase_rows(session, headers, history_URL, history_search_URL, target_datetimes, first_html)`: ページ検索とチェックボックス選択

**修正済み main メソッド**:
- 各選択された購入記録について詳細ページを取得
- receiptInfo に変換
- NewReceiptRegistration API に送信
- 登録統計を返却

**新規インポート**:
```python
from src.api.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
```

## 次のステップ

### 1. HTML セレクタの調整
実際のベルク明細ページの HTML 構造に基づいて、以下のセレクタを調整してください：
- 日付抽出: `input[name='Date']`
- 商品行: `tr[data-item]`, `.receipt-detail-row`
- 商品名: `.item-name`, `[data-item-name]`
- 数量: `.quantity`, `[data-quantity]`
- 単価: `.unit-price`, `[data-unit-price]`
- 合計: `.total-price`, `[data-total-price]`

### 2. ページネーション最大値の取得
`select_purchase_rows` メソッド内の max_page 抽出ロジックをベルクの HTML 構造に合わせて調整してください。

### 3. 詳細ページの POSTデータ
`fetch_receipt_detail` メソッドの form_data を、ベルクの実際の POST 要件に合わせて調整してください。

### 4. テスト
- 実際のベルク会員サイトで動作確認
- エラーハンドリングと例外ケースのテスト
- 複数ページにわたる購入履歴のテスト

## エラーハンドリング

main メソッドは各レシート登録の失敗をキャッチしてログに記録し、他の記録の処理を続行します：

```python
except Exception as e:
    self.logger.error(f"Failed to register receipt: {e}")
```

これにより、1つのレシートの問題が全体のバッチ処理をブロックしないようになります。

## 返却値

```python
{
    "need_to_register": <未登録レシート数>,
    "registered": <実際に登録されたレシート数>
}
```
