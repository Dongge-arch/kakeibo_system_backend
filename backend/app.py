# SPDX-License-Identifier: MIT

import os
import sys
import io
import hmac

from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles


def resource_path(path):
    """
    PyInstaller配布時と通常実行時の両方でプロジェクト内パスを解決する。

    Args:
        path (str): プロジェクトルートからの相対パス。

    Returns:
        str: 実行環境に合わせて解決した絶対パス。
    """
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, path)


# src配下のimportを通常実行・exe配布の両方で安定させる。
SRC_ROOT = resource_path("")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from src.api.budget.budget_reference.budgetReference import BudgetReference
from src.api.budget.new_budget_registration.newBudgetRegistration import NewBudgetRegistration
from src.api.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.api.receipt.receipt_reference.receiptReference import ReceiptReference
from src.api.receipt.receipt_update_delete.receiptUpdateDelete import ReceiptUpdateDelete
from src.api.receipt.recurring_expense.recurringExpenseApi import RecurringExpenseApi
from src.api.budget.budget_batch.budgetBatchApi import BudgetBatchApi
from src.api.income.income.incomeApi import IncomeApi
from src.api.master.master_data.masterDataApi import MasterDataApi
from src.api.receipt.ai_receipt.aiReceiptApi import AiReceiptApi
from src.api.receipt.receipt_export.receiptExport import ReceiptExportService
from src.api.settings.app_settings.appSettingsApi import AppSettingsApi
from src.api.settings.user_auth.userAuthApi import UserAuthApi
from src.api.utils import call_api, json_response, normalize_invoice_number, normalize_receipt_number
from src.common.auth_context import reset_current_user, set_current_user
from src.common.auth_token import verify_token
from src.common.config import APP_CONFIG


app = FastAPI()
# エクスポート用の一時データを保持するサービス。
receipt_export = ReceiptExportService()

AI_RECEIPT_CONFIG = APP_CONFIG.get("ai_receipt", {})
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or AI_RECEIPT_CONFIG.get("gemini_api_key", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or AI_RECEIPT_CONFIG.get("gemini_model", "gemini-2.5-flash-lite")
API_GATEWAY_CONFIG = APP_CONFIG.get("api_gateway", {})
APP_API_KEY = os.environ.get("KAKEIBO_API_KEY") or API_GATEWAY_CONFIG.get("api_key", "")
# Lambdaでは静的配信を止めるためのスイッチ。
SERVE_STATIC = os.environ.get("KAKEIBO_SERVE_STATIC", "true").lower() in ("1", "true", "yes", "on")
REACT_DIST_DIR = resource_path("frontend-react/dist")
LEGACY_FRONTEND_DIR = resource_path("frontend")
USE_REACT_FRONTEND = os.path.exists(os.path.join(REACT_DIST_DIR, "index.html"))
FRONTEND_CORS_ORIGIN = os.environ.get("FRONTEND_CORS_ORIGIN", "*")

cors_origins = [
    origin.strip()
    for origin in FRONTEND_CORS_ORIGIN.split(",")
    if origin.strip()
]
if not cors_origins:
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "accept",
        "authorization",
        "cache-control",
        "content-type",
        "pragma",
        "x-api-key",
        "x-kakeibo-user-id",
        "x-kakeibo-user-email",
        "x-kakeibo-user-name",
        "x-kakeibo-user-nickname",
    ],
)


def local_api(api_class, body=None, default_status_code=200, **kwargs):
    """
    APIクラスを生成して共通レスポンス形式で呼び出す。

    Args:
        api_class (type): 呼び出すBaseRestApi派生クラス。
        body (dict | None): APIへ渡すリクエスト本文。
        default_status_code (int): APIがstatusCodeを返さない場合の既定HTTPステータス。
        **kwargs: APIクラスのコンストラクタへ渡す追加設定。
    """
    api = api_class(**kwargs)
    return call_api(api, body or {}, default_status_code=default_status_code)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    """
    認証ユーザーをDB層へ渡し、静的ファイルのキャッシュを抑止する。

    /user配下以外の未ログイン操作は匿名ユーザー領域として扱い、
    ログイン済み操作はJWT内のuserIdでDB検索・更新を絞り込む。
    """
    if not is_allowed_without_app_api_key(request.url.path, request.method):
        supplied_api_key = request.headers.get("x-api-key") or ""
        if APP_API_KEY and not hmac.compare_digest(supplied_api_key, APP_API_KEY):
            return JSONResponse(
                {"errorMessage": "API key is required."},
                status_code=403,
            )

    auth_header = request.headers.get("Authorization") or ""
    # Authorization: Bearer <token> からJWTだけを取り出す。
    token_value = auth_header.replace("Bearer ", "", 1).strip()
    # ユーザー未ログイン時の業務データは匿名ユーザー領域へ入れる。
    session = verify_token(token_value) if token_value else None
    is_public = is_allowed_without_app_api_key(request.url.path, request.method)
    is_account_api = request.url.path.startswith("/user/")
    if not is_public and not is_account_api and not session:
        return JSONResponse(
            {"errorMessage": "ログインが必要です。"},
            status_code=401,
        )

    header_user = {
        "userId": request.headers.get("x-kakeibo-user-id") or "",
        "email": request.headers.get("x-kakeibo-user-email") or "",
        "username": request.headers.get("x-kakeibo-user-name") or "",
        "nickname": request.headers.get("x-kakeibo-user-nickname") or "",
    }
    token_user = session or {}
    context_user = {
        "userId": "" if is_account_api else (header_user.get("userId") or token_user.get("userId", "")),
        "email": header_user.get("email") or token_user.get("email") or token_user.get("username") or "",
        "username": header_user.get("username") or token_user.get("username") or token_user.get("email") or "",
        "nickname": header_user.get("nickname") or token_user.get("nickname") or "",
    }
    context_token = set_current_user(context_user)
    try:
        response = await call_next(request)
        if (
            request.url.path == "/"
            or request.url.path.startswith("/assets/")
            or request.url.path.startswith("/static/")
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    finally:
        reset_current_user(context_token)


def is_allowed_without_app_api_key(path: str, method: str) -> bool:
    """
    アプリAPIキーなしで通してよいリクエストか判定する。

    Args:
        path (str): リクエストパス。
        method (str): HTTPメソッド。

    Returns:
        bool: APIキーなしで通す場合はTrue。
    """
    if method.upper() == "OPTIONS":
        return True
    return (
        path == "/"
        or path.startswith("/assets/")
        or path.startswith("/static/")
        or path.startswith("/export/receipt/page/")
        or path.startswith("/export/receipt/file/")
        or path == "/favicon.ico"
    )


@app.options("/{full_path:path}")
def cors_preflight(full_path: str):
    return JSONResponse({"ok": True})


if SERVE_STATIC:
    if USE_REACT_FRONTEND:
        app.mount("/assets", StaticFiles(directory=os.path.join(REACT_DIST_DIR, "assets")), name="assets")
    else:
        app.mount("/static", StaticFiles(directory=LEGACY_FRONTEND_DIR), name="static")

    @app.get("/")
    def read_index():
        """
        React版または旧版フロントエンドのindex.htmlを返す。
        """
        if USE_REACT_FRONTEND:
            return FileResponse(os.path.join(REACT_DIST_DIR, "index.html"))
        return FileResponse(os.path.join(LEGACY_FRONTEND_DIR, "index.html"))


@app.post("/export/receipt/prepare")
def prepare_receipt_export(request: dict = Body(...)):
    """
    レシート検索結果の出力準備を行い、ダウンロードページURLを返す。

    Args:
        request (dict): 出力対象と形式を含むリクエスト本文。
    """
    return receipt_export.prepare(request)


@app.get("/export/receipt/page/{token}", response_class=HTMLResponse)
def receipt_export_page(token: str):
    """
    出力トークンに紐づくダウンロード確認ページを返す。

    Args:
        token (str): 出力準備時に発行された一時トークン。
    """
    html = receipt_export.page_html(token)
    if not html:
        return HTMLResponse(
            """
            <!doctype html>
            <html lang="ja">
              <head><meta charset="utf-8"><title>出力エラー</title></head>
              <body style="font-family:'Yu Gothic',sans-serif;padding:32px;">
                <h1>出力データが見つかりません</h1>
                <p>検索画面からもう一度出力してください。</p>
              </body>
            </html>
            """,
            status_code=404,
        )
    return HTMLResponse(html)


@app.get("/export/receipt/file/{token}")
def receipt_export_file(token: str):
    """
    出力トークンに紐づくファイルを生成して返す。

    Args:
        token (str): 出力準備時に発行された一時トークン。
    """
    file_data = receipt_export.build_file(token)
    if not file_data:
        return HTMLResponse("出力データが見つかりません。", status_code=404)
    return StreamingResponse(
        io.BytesIO(file_data["content"]),
        media_type=file_data["media_type"],
        headers=receipt_export.attachment_headers(file_data["filename"]),
    )


@app.get("/app/settings")
def get_app_settings():
    """
    現在ユーザーのアプリ表示設定を取得する。
    """
    return local_api(AppSettingsApi, {"action": "get"})


@app.post("/app/settings")
def upsert_app_settings(request: dict = Body(...)):
    """
    現在ユーザーのアプリ表示設定を保存する。

    Args:
        request (dict): 保存する表示設定。
    """
    return local_api(AppSettingsApi, {"action": "save", "settings": request})


@app.post("/user/register")
def register_user(request: dict = Body(...)):
    """
    メールアドレスとパスワードで新規ユーザーを登録する。

    Args:
        request (dict): email、password、nicknameを含む登録情報。
    """
    return local_api(UserAuthApi, {"action": "register", **(request or {})})


@app.post("/user/login")
def login_user(request: dict = Body(...)):
    """
    メールアドレスとパスワードでログインし、端末保存用セッションを返す。

    Args:
        request (dict): emailとpasswordを含むログイン情報。
    """
    return local_api(UserAuthApi, {"action": "login", **(request or {})})


@app.post("/user/password-reset/request")
def request_password_reset(request: dict = Body(...)):
    """
    パスワード再設定コードを発行し、DBへ保存する。
    """
    return local_api(UserAuthApi, {"action": "request_password_reset", **(request or {})})


@app.post("/user/password-reset/confirm")
def confirm_password_reset(request: dict = Body(...)):
    """
    再設定コードを検証し、新しいパスワードへ更新する。
    """
    return local_api(UserAuthApi, {"action": "reset_password", **(request or {})})


@app.post("/user/logout")
def logout_user(request: dict = Body(...)):
    """
    クライアント側ログアウト処理に合わせて成功レスポンスを返す。

    Args:
        request (dict): ログアウト要求本文。
    """
    return local_api(UserAuthApi, {"action": "logout", **(request or {})})


@app.post("/user/me")
def get_current_user(request: dict = Body(...)):
    """
    保存済みトークンから現在ログイン中のユーザー情報を再取得する。

    Args:
        request (dict): tokenを含むセッション確認要求。
    """
    return local_api(UserAuthApi, {"action": "me", **(request or {})})


@app.post("/user/profile")
def update_user_profile(request: dict = Body(...)):
    """
    ログイン中ユーザーの表示名とアイコン画像を更新する。
    """
    return local_api(UserAuthApi, {"action": "update_profile", **(request or {})})


@app.get("/dashboard/layout")
def get_dashboard_layout():
    """
    ダッシュボードカードの並び順と表示サイズを取得する。
    """
    return local_api(AppSettingsApi, {"action": "get_dashboard_layout"})


@app.post("/dashboard/layout")
def save_dashboard_layout(request: dict = Body(...)):
    """
    ダッシュボードカードの並び順と表示サイズを保存する。

    Args:
        request (dict): layout配列を含む保存要求。
    """
    return local_api(AppSettingsApi, {"action": "save_dashboard_layout", "layout": (request or {}).get("layout") or []})


@app.get("/budget/budgets")
def get_budgets():
    """
    現在ユーザーの予算一覧を取得する。
    """
    return local_api(BudgetBatchApi, {"action": "list"})


@app.post("/budget/budgets")
def upsert_budgets(request: dict = Body(...)):
    """
    分類別予算を一括登録または更新する。

    Args:
        request (dict): budgets配列を含む保存要求。
    """
    return local_api(BudgetBatchApi, {"action": "upsert", "budgets": (request or {}).get("budgets") or []})


@app.post("/receipt/newReceiptRegistration")
def create_receipt(request: dict = Body(...)):
    """
    レシートヘッダと明細を新規登録する。

    インボイス登録番号はT+13桁へ正規化してから業務APIへ渡す。

    Args:
        request (dict): receiptInfoを含む登録要求。
    """
    receipt_info = (request or {}).get("receiptInfo", {})
    invoice_number = normalize_receipt_number(receipt_info.get("invoiceRegistrationNumber"))
    receipt_info["invoiceRegistrationNumber"] = invoice_number or ""
    return local_api(NewReceiptRegistration, request, default_status_code=201)


@app.post("/receipt/receiptReference")
def get_receipt(request: dict = Body(...)):
    """
    条件に一致するレシート一覧と明細を取得する。

    インボイス登録番号が指定された場合は検索前に形式を正規化する。

    Args:
        request (dict): 日付、金額、分類などの検索条件。
    """
    invoice_number = (request or {}).get("invoiceRegistrationNumber")
    if invoice_number:
        normalized = normalize_receipt_number(invoice_number)
        if not normalized:
            return json_response(400, {"errorMessage": "登録番号は T/A + 13桁で指定してください。"})
        request["invoiceRegistrationNumber"] = normalized
    return local_api(ReceiptReference, request)


@app.get("/recurring-expenses")
def list_recurring_expenses():
    """定期出費設定の一覧を取得する。"""
    return local_api(RecurringExpenseApi, {"action": "list"})


@app.post("/recurring-expenses")
def create_recurring_expense(request: dict = Body(...)):
    """定期出費設定を登録する。"""
    return local_api(RecurringExpenseApi, {"action": "create", **(request or {})}, default_status_code=201)


@app.put("/recurring-expenses/{rule_id}")
def update_recurring_expense(rule_id: int, request: dict = Body(...)):
    """定期出費設定を更新する。"""
    return local_api(RecurringExpenseApi, {"action": "update", "id": rule_id, **(request or {})})


@app.delete("/recurring-expenses/{rule_id}")
def delete_recurring_expense(rule_id: int):
    """定期出費設定を削除する。"""
    return local_api(RecurringExpenseApi, {"action": "delete", "id": rule_id})


@app.post("/recurring-expenses/run-due")
def run_due_recurring_expenses():
    """ログイン時などに期限到来した定期出費を自動登録する。"""
    return local_api(RecurringExpenseApi, {"action": "run_due"})


@app.put("/receipt/ReceiptUpdateDelete")
def update_delete_receipt(request: dict = Body(...)):
    """
    レシート情報の更新または削除を実行する。

    Args:
        request (dict): actionと対象レシート情報を含む更新・削除要求。
    """
    receipt_info = (request or {}).get("receiptInfo") or {}
    if receipt_info:
        invoice_number = normalize_receipt_number(receipt_info.get("invoiceRegistrationNumber"))
        receipt_info["invoiceRegistrationNumber"] = invoice_number or ""
    return local_api(ReceiptUpdateDelete, request)


@app.post("/ai/receipt/analyze")
def analyze_receipt_with_ai(request: dict = Body(...)):
    """
    画像からAIレシート解析を実行する。

    Args:
        request (dict): 解析対象画像と補助情報。
    """
    return local_api(
        AiReceiptApi,
        {"action": "analyze", **(request or {})},
        gemini_api_key=GEMINI_API_KEY,
        gemini_model=GEMINI_MODEL,
    )


@app.get("/ai/receipt/usage")
def get_ai_receipt_usage():
    """
    AIレシート解析の利用量サマリーを取得する。
    """
    return local_api(
        AiReceiptApi,
        {"action": "usage"},
        gemini_api_key=GEMINI_API_KEY,
        gemini_model=GEMINI_MODEL,
    )


@app.get("/ai/receipt/history")
def get_ai_receipt_history():
    """
    AIレシート解析履歴の一覧を取得する。
    """
    return local_api(
        AiReceiptApi,
        {"action": "list_history"},
        gemini_api_key=GEMINI_API_KEY,
        gemini_model=GEMINI_MODEL,
    )


@app.get("/ai/receipt/history/{analysis_id}")
def get_ai_receipt_history_detail(analysis_id: str):
    """
    指定したAIレシート解析履歴の詳細を取得する。

    Args:
        analysis_id (str): AI解析履歴ID。
    """
    return local_api(
        AiReceiptApi,
        {"action": "get_history", "analysisId": analysis_id},
        gemini_api_key=GEMINI_API_KEY,
        gemini_model=GEMINI_MODEL,
    )


@app.post("/ai/receipt/history/final")
def save_ai_receipt_final(request: dict = Body(...)):
    """
    AI解析結果をユーザー編集後の確定内容として保存する。

    Args:
        request (dict): 確定保存するレシート情報。
    """
    return local_api(
        AiReceiptApi,
        {"action": "save_final_receipt", **(request or {})},
        gemini_api_key=GEMINI_API_KEY,
        gemini_model=GEMINI_MODEL,
    )


@app.get("/receipt/getcategory1")
def get_category1():
    """
    支出の大分類一覧を取得する。
    """
    return local_api(MasterDataApi, {"action": "list_category1"})


@app.post("/receipt/addcategory1")
def add_category1(request: dict = Body(...)):
    """
    支出の大分類を追加する。

    Args:
        request (dict): 追加する大分類名。
    """
    return local_api(MasterDataApi, {"action": "add_category1", **(request or {})}, default_status_code=201)


@app.put("/receipt/deletecategory1")
def delete_category1(request: dict = Body(...)):
    """
    支出の大分類を論理削除する。

    Args:
        request (dict): 削除対象の大分類名。
    """
    return local_api(MasterDataApi, {"action": "delete_category1", **(request or {})})


@app.get("/receipt/getcategory2")
def get_category2():
    """
    支出の小分類一覧を取得する。
    """
    return local_api(MasterDataApi, {"action": "list_category2"})


@app.post("/receipt/addcategory2")
def add_category2(request: dict = Body(...)):
    """
    支出の小分類を追加する。

    Args:
        request (dict): 追加する大分類、小分類、税率。
    """
    return local_api(MasterDataApi, {"action": "add_category2", **(request or {})}, default_status_code=201)


@app.post("/receipt/adddefaultcategories")
def add_default_categories(request: dict = Body(...)):
    """
    画面から渡された標準の出費分類・小分類・入金分類を一括追加する。

    Args:
        request (dict): category1、category2、salaryCategoriesを含む標準分類。
    """
    return local_api(MasterDataApi, {"action": "add_default_categories", **(request or {})})


@app.put("/receipt/deletecategory2")
def delete_category2(request: dict = Body(...)):
    """
    支出の小分類を論理削除する。

    Args:
        request (dict): 削除対象の大分類と小分類。
    """
    return local_api(MasterDataApi, {"action": "delete_category2", **(request or {})})


@app.get("/receipt/getSupplierByInvoice")
def get_supplier_by_invoice(invoiceNo: str):
    """
    インボイス登録番号から店舗・取引先情報を取得する。

    Args:
        invoiceNo (str): T+13桁、または13桁のインボイス登録番号。
    """
    return local_api(MasterDataApi, {"action": "supplier_by_invoice", "invoiceNo": invoiceNo})


@app.post("/receipt/addsalarycategory")
def add_salary_category(request: dict = Body(...)):
    """
    入金分類を追加する。

    Args:
        request (dict): 追加する入金分類名。
    """
    return local_api(MasterDataApi, {"action": "add_salary_category", **(request or {})}, default_status_code=201)


@app.get("/receipt/getsalarycategory")
def get_salary_category():
    """
    入金分類一覧を取得する。
    """
    return local_api(MasterDataApi, {"action": "list_salary_category"})


@app.put("/receipt/deletesalarycategory")
def delete_salary_category(request: dict = Body(...)):
    """
    入金分類を論理削除する。

    Args:
        request (dict): 削除対象の入金分類名。
    """
    return local_api(MasterDataApi, {"action": "delete_salary_category", **(request or {})})


@app.get("/receipt/getinvoice")
def get_invoice_category():
    """
    インボイス登録マスタ一覧を取得する。
    """
    return local_api(MasterDataApi, {"action": "list_invoice"})


@app.put("/receipt/deleteinvoice")
def delete_invoice_category(request: dict = Body(...)):
    """
    インボイス登録マスタを論理削除する。

    Args:
        request (dict): 削除対象のインボイス登録番号。
    """
    return local_api(MasterDataApi, {"action": "delete_invoice", **(request or {})})


@app.post("/receipt/updateinvoice")
def update_invoice_category(request: dict = Body(...)):
    """
    インボイス登録マスタの店舗名・税区分・画像を更新する。

    Args:
        request (dict): 更新対象の店舗名、税区分、画像。
    """
    return local_api(MasterDataApi, {"action": "update_invoice", **(request or {})})


@app.post("/receipt/salaryregistration")
def create_salary_info(request: dict = Body(...)):
    """
    入金情報を新規登録する。

    Args:
        request (dict): 入金日、分類、金額などの登録情報。
    """
    return local_api(IncomeApi, {"action": "create", **(request or {})}, default_status_code=201)


@app.get("/receipt/getincome")
def get_income(month: str = Query(None), dateFrom: str = Query(None), dateTo: str = Query(None)):
    """
    月または日付範囲に一致する入金情報を取得する。

    Args:
        month (str | None): yyyy-mm形式の対象月。
        dateFrom (str | None): 検索開始日。
        dateTo (str | None): 検索終了日。
    """
    return local_api(IncomeApi, {
        "action": "list",
        "month": month,
        "dateFrom": dateFrom,
        "dateTo": dateTo,
    })


@app.put("/receipt/updateincome")
def update_income(request: dict = Body(...)):
    """
    入金情報を更新する。

    Args:
        request (dict): 更新対象の入金情報。
    """
    return local_api(IncomeApi, {"action": "update", **(request or {})})


@app.put("/receipt/deleteincome")
def delete_income(request: dict = Body(...)):
    """
    入金情報を論理削除する。

    Args:
        request (dict): 削除対象の入金情報。
    """
    return local_api(IncomeApi, {"action": "delete", **(request or {})})


@app.post("/budget/budgetregistration")
def budget_registration_new(request: dict = Body(...)):
    """
    予算情報を新規登録する。

    Args:
        request (dict): 登録する予算情報。
    """
    return local_api(NewBudgetRegistration, request, default_status_code=201)


@app.post("/budget/budgetreference")
def budget_reference(request: dict = Body(...)):
    """
    条件に一致する予算情報を取得する。

    Args:
        request (dict): 予算検索条件。
    """
    return local_api(BudgetReference, request)
