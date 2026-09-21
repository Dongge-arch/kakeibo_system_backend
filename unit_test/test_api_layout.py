"""API分割後のルーティングとデプロイ構造を検証する。"""

import importlib.util
from pathlib import Path
import re
from unittest.mock import MagicMock

import pytest

from src.api.kakeibo.master.category1.category1Registration import Category1Registration
from src.api.kakeibo.master.category1.category1Reference import Category1Reference
from src.api.kakeibo.master.category1.category1UpdateDelete import Category1UpdateDelete
from src.api.kakeibo.master.category2.category2Registration import Category2Registration
from src.api.kakeibo.master.category2.category2Reference import Category2Reference
from src.api.kakeibo.master.category2.category2UpdateDelete import Category2UpdateDelete
from src.api.kakeibo.master.invoice.invoiceReference import InvoiceReference
from src.api.kakeibo.master.invoice.invoiceUpdateDelete import InvoiceUpdateDelete
from src.api.kakeibo.master.salary_category.salaryCategoryRegistration import SalaryCategoryRegistration
from src.api.kakeibo.master.salary_category.salaryCategoryReference import SalaryCategoryReference
from src.api.kakeibo.master.salary_category.salaryCategoryUpdateDelete import SalaryCategoryUpdateDelete
from src.api.kakeibo.income.income_reference.incomeReference import IncomeReference
from src.api.kakeibo.budget.budget_api.budgetList import BudgetList
from src.api.kakeibo.budget.budget_api.budgetUpsert import BudgetUpsert
from src.api.kakeibo.receipt.recurring_expense.reference.recurringExpenseReference import RecurringExpenseReference
from src.api.kakeibo.receipt.recurring_expense.registration.recurringExpenseRegistration import RecurringExpenseRegistration
from src.api.kakeibo.receipt.recurring_expense.update_delete.recurringExpenseUpdateDelete import RecurringExpenseUpdateDelete
from src.api.kakeibo.receipt.recurring_expense.run_due.recurringExpenseRunDue import RecurringExpenseRunDue
from src.api.kakeibo.settings.app_settings.appSettingsReference import AppSettingsReference
from src.api.kakeibo.settings.app_settings.appSettingsRegistration import AppSettingsRegistration
from src.api.kakeibo.settings.app_settings.dashboardLayoutReference import DashboardLayoutReference
from src.api.kakeibo.settings.app_settings.dashboardLayoutRegistration import DashboardLayoutRegistration
from src.api.kakeibo.settings.user_auth.userRegistration import UserRegistration
from src.api.kakeibo.settings.user_auth.userLogin import UserLogin
from src.api.kakeibo.settings.user_auth.userLogout import UserLogout
from src.api.kakeibo.settings.user_auth.userReference import UserReference
from src.api.kakeibo.settings.user_auth.userProfileUpdate import UserProfileUpdate
from src.api.kakeibo.settings.user_auth.passwordResetRequest import PasswordResetRequest
from src.api.kakeibo.settings.user_auth.passwordResetConfirm import PasswordResetConfirm
from src.api.kakeibo.settings.auto_linkage.autoLinkageReference import AutoLinkageReference
from src.api.kakeibo.settings.auto_linkage.autoLinkageDetail import AutoLinkageDetail
from src.api.kakeibo.settings.auto_linkage.autoLinkageUpdateDelete import AutoLinkageUpdateDelete
from src.api.kakeibo.settings.auto_linkage.autoLinkageLogin import AutoLinkageLogin
from src.api.kakeibo.settings.auto_linkage.autoLinkageRun import AutoLinkageRun
from src.api.kakeibo.receipt.receipt_update_delete.receiptUpdateDelete import ReceiptUpdateDelete
from src.common.auth_token import issue_token
from src.common.functions.response import response
from src.common.database.postgresql import Postgresql


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("api_type,operation", [
    (Category1Registration, "add_category1"),
    (Category1Reference, "list_category1"),
    (Category1UpdateDelete, "delete_category1"),
    (Category2Registration, "add_category2"),
    (Category2Reference, "list_category2"),
    (Category2UpdateDelete, "delete_category2"),
    (InvoiceReference, "list_invoice"),
    (SalaryCategoryRegistration, "add_salary_category"),
    (SalaryCategoryReference, "list_salary_category"),
    (SalaryCategoryUpdateDelete, "delete_salary_category"),
])
def test_master_api_calls_only_its_operation(api_type, operation):
    api = api_type.__new__(api_type)
    api.require_user_id = lambda request: "user-1"
    setattr(api, operation, lambda *args: args)
    result = api.main({"body": {"name": "test"}})
    assert result[-1] == "user-1"


def test_invoice_update_delete_share_one_api():
    api = InvoiceUpdateDelete.__new__(InvoiceUpdateDelete)
    api.require_user_id = lambda request: "user-1"
    api.update_invoice = lambda body, user_id: ("update", user_id)
    api.delete_invoice = lambda body, user_id: ("delete", user_id)
    assert api.main({"body": {"action": "update"}}) == ("update", "user-1")
    assert api.main({"body": {"action": "delete"}}) == ("delete", "user-1")


def test_response_accepts_list_or_empty_body():
    assert response(200, [1]) == {"statusCode": 200, "body": [1]}
    assert response(204, None) == {"statusCode": 204, "body": None}


def test_income_reference_uses_shared_response_function():
    api = IncomeReference.__new__(IncomeReference)
    api.require_user_id = lambda request: "user-1"
    api.database = MagicMock()
    api.database.read_sql.return_value = "SELECT * FROM SALARY_INFO"
    api.database.select.return_value = []
    assert api.main({"body": {}}) == response(200, [])


def test_budget_endpoints_delegate_to_one_operation():
    listing = BudgetList.__new__(BudgetList)
    listing.require_user_id = lambda request: "user-1"
    listing.list_budgets = lambda user_id: [{"user": user_id}]
    assert listing.main({"body": {"action": "upsert"}}) == response(200, [{"user": "user-1"}])

    saving = BudgetUpsert.__new__(BudgetUpsert)
    saving.require_user_id = lambda request: "user-1"
    saving.upsert_budgets = MagicMock()
    assert saving.main({"body": {"budgets": [{"category1": "food"}]}}) == response(200, {"ok": True})
    saving.upsert_budgets.assert_called_once_with([{"category1": "food"}], "user-1")


@pytest.mark.parametrize("api_type,method,body", [
    (RecurringExpenseReference, "list_rules", {}),
    (RecurringExpenseRegistration, "create_rule", {"ruleName": "rent"}),
    (RecurringExpenseRunDue, "run_due", {}),
])
def test_recurring_endpoints_delegate_to_one_operation(api_type, method, body):
    api = api_type.__new__(api_type)
    api.require_user_id = lambda request: "user-1"
    operation = MagicMock(return_value=response(200, {"ok": True}))
    setattr(api, method, operation)
    assert api.main({"body": body}) == response(200, {"ok": True})
    if method == "create_rule":
        operation.assert_called_once_with(body, "user-1")
    else:
        operation.assert_called_once_with("user-1")


def test_recurring_update_delete_share_one_api():
    api = RecurringExpenseUpdateDelete.__new__(RecurringExpenseUpdateDelete)
    api.require_user_id = lambda request: "user-1"
    api.update_rule = lambda body, user_id: ("update", user_id)
    api.delete_rule = lambda body, user_id: ("delete", user_id)
    assert api.main({"body": {"action": "update"}}) == ("update", "user-1")
    assert api.main({"body": {"action": "delete"}}) == ("delete", "user-1")


@pytest.mark.parametrize("api_type,operation,body,expected", [
    (AppSettingsReference, "get_settings", {}, {"budgetEnabled": True}),
    (DashboardLayoutReference, "get_dashboard_layout", {}, ["summary"]),
    (AppSettingsRegistration, "save_settings", {"settings": {"budgetEnabled": True}}, {"ok": True}),
    (DashboardLayoutRegistration, "save_dashboard_layout", {"layout": ["summary"]}, {"ok": True}),
])
def test_settings_endpoints_delegate_to_one_operation(api_type, operation, body, expected):
    api = api_type.__new__(api_type)
    api.require_user_id = lambda request: "user-1"
    handler = MagicMock(return_value=expected)
    setattr(api, operation, handler)
    assert api.main({"body": body}) == response(200, expected)
    if operation.startswith("save"):
        handler.assert_called_once_with(next(iter(body.values())), "user-1")
    else:
        handler.assert_called_once_with("user-1")


@pytest.mark.parametrize("api_type,operation", [
    (UserRegistration, "register"),
    (UserLogin, "login"),
    (UserLogout, "logout"),
    (UserReference, "me"),
    (UserProfileUpdate, "update_profile"),
    (PasswordResetRequest, "request_password_reset"),
    (PasswordResetConfirm, "reset_password"),
])
def test_account_endpoints_delegate_to_one_operation(api_type, operation):
    api = api_type.__new__(api_type)
    handler = MagicMock(return_value=response(200, {"ok": True}))
    setattr(api, operation, handler)
    body = {"action": "unrelated"}
    assert api.main({"body": body}) == response(200, {"ok": True})
    handler.assert_called_once_with(body)


def test_profile_uses_signed_user_not_request_user_id(monkeypatch):
    monkeypatch.setenv("KAKEIBO_JWT_SECRET", "test-profile-secret")
    api = object.__new__(UserProfileUpdate)
    api.database = MagicMock()
    api.database.select.return_value = [{"USER_ID": "owner", "USER_NAME": "owner@example.com", "NICKNAME": "Owner"}]
    token = issue_token({"userId": "owner", "username": "owner@example.com"})
    result = api.update_profile({"token": token, "userId": "another-account", "nickname": "Owner"})
    assert result["statusCode"] == 200
    assert api.database.update.call_args.args[1]["USER_ID"] == "owner"

    api.database.reset_mock()
    assert api.update_profile({"userId": "another-account", "nickname": "Wrong"})["statusCode"] == 401
    api.database.update.assert_not_called()


def test_auto_linkage_endpoints_delegate_without_dispatch():
    for api_type, operation in (
        (AutoLinkageReference, "list_places"),
        (AutoLinkageDetail, "get_place"),
        (AutoLinkageLogin, "login_place"),
        (AutoLinkageRun, "run_place"),
    ):
        api = object.__new__(api_type)
        api.require_user_id = lambda request: "user-1"
        handler = MagicMock(return_value=response(200, {"ok": True}) if operation == "run_place" else {"ok": True})
        setattr(api, operation, handler)
        result = api.main({"body": {"connectionType": "BELC"}})
        assert result == response(200, {"ok": True})
        assert handler.call_count == 1


def test_auto_linkage_update_and_delete_share_one_api():
    api = object.__new__(AutoLinkageUpdateDelete)
    api.require_user_id = lambda request: "user-1"
    api.update_place = lambda body, user_id: {"method": "update", "user": user_id}
    api.delete_place = lambda body, user_id: {"method": "delete", "user": user_id}
    assert api.main({"body": {"action": "update"}}) == response(200, {"method": "update", "user": "user-1"})
    assert api.main({"body": {"action": "delete"}}) == response(200, {"method": "delete", "user": "user-1"})


def test_every_sam_function_has_one_handler_and_log_group():
    template = (ROOT / "template.yaml").read_text(encoding="utf-8")
    packages = re.findall(r"CodeUri: dist_lambda/function/([a-z0-9_]+)", template)
    assert len(packages) == len(set(packages)) == 56
    assert template.count("LoggingConfig:") == 56
    for name in packages:
        sources = [ROOT / folder / name / "lambda_handler.py" for folder in ("lambda_api", "lambda_batch")]
        found = [path for path in sources if path.is_file()]
        assert len(found) == 1, name
        assert sorted(path.name for path in found[0].parent.iterdir() if path.is_file()) == ["lambda_handler.py"]
        specification = importlib.util.spec_from_file_location(f"test_lambda_{name}", found[0])
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        assert callable(module.lambda_handler)


def test_sql_file_cache_uses_location_as_well_as_name():
    database = Postgresql.__new__(Postgresql)
    database._sql_cache = {}
    first = database.read_sql("SELECT_BUDGET_INFO", location=str(ROOT / "src/api/kakeibo/budget/budget_api/budgetBase.py"))
    second = database.read_sql("SELECT_BUDGET_INFO", location=str(ROOT / "src/api/kakeibo/budget/budget_reference/budgetReference.py"))
    assert first != second


def test_legacy_parameters_are_bound_to_column_names():
    database = Postgresql.__new__(Postgresql)
    database.connector = MagicMock()
    database.logger = MagicMock()
    database.do_sql_with_retry(
        "UPDATE AUTO_INPUT_INFO SET LAST_LOGIN_STATUS=%(LAST_LOGIN_STATUS)s, "
        "SUICA_COOKIE_JSON=%(SUICA_COOKIE_JSON)s WHERE CRE_USER_ID=%(CRE_USER_ID)s",
        {"STATUS": "AUTHENTICATED", "COOKIE_JSON": "{}", "USER_ID": "user-1"},
    )
    assert database.connector.execute.call_args.args[1] == {
        "LAST_LOGIN_STATUS": "AUTHENTICATED",
        "SUICA_COOKIE_JSON": "{}",
        "CRE_USER_ID": "user-1",
    }


def test_named_sql_parameters_use_existing_uppercase_columns():
    for root in (ROOT / "src/api", ROOT / "src/batch", ROOT / "src/common/base"):
        for path in root.rglob("*.sql"):
            sql = path.read_text(encoding="utf-8")
            without_parameters = re.sub(r"%\([A-Za-z0-9_]+\)s", "", sql)
            for name in re.findall(r"%\(([A-Za-z0-9_]+)\)s", sql):
                assert name == name.upper(), path
                assert re.search(rf"\b{re.escape(name)}\b", without_parameters), (path, name)


def test_receipt_update_delete_reads_sql_files_and_binds_owner():
    api = object.__new__(ReceiptUpdateDelete)
    api.database = MagicMock()
    api.database.read_sql.side_effect = lambda name, location: (Path(location).parent / "sql" / f"{name}.sql").read_text()
    api.delete_receipt_info_and_details("receipt-1", "owner-1")
    assert api.database.update.call_count == 2
    for call in api.database.update.call_args_list:
        sql = call.args[0]
        params = call.kwargs["params"]
        assert "RET_ID = %(RET_ID)s" in sql
        assert "CRE_USER_ID = %(CRE_USER_ID)s" in sql
        assert params["RET_ID"] == "receipt-1"
        assert params["CRE_USER_ID"] == params["UPD_USER_ID"] == "owner-1"

    api.logo_storage = MagicMock()
    api.database.update.return_value = 0
    api.upsert_invoice_registration({"invoiceRegistrationNumber": "T1234567890123", "supplierName": "Store"}, "owner-1")
    assert api.database.insert.call_args.kwargs["params"]["CRE_USER_ID"] == "owner-1"


def test_schema_ddl_is_stored_in_sql_files():
    for directory in (
        ROOT / "src/api/kakeibo/receipt/ai_receipt/sql",
        ROOT / "src/api/kakeibo/settings/user_auth/sql",
        ROOT / "src/api/kakeibo/receipt/receipt_update_delete/sql",
    ):
        for path in directory.glob("*.sql"):
            if path.name.startswith(("CREATE_", "ALTER_")):
                assert path.read_text(encoding="utf-8").lstrip().startswith(("CREATE ", "ALTER "))
