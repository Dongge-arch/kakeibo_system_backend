"""Normalize API class method docstrings to the receipt registration style."""

import argparse
import ast
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = (ROOT / "src" / "api", ROOT / "src" / "batch", ROOT / "src" / "common" / "base")
ARG_DESCRIPTIONS = {
    "request_dict": "API呼び出し時のリクエスト情報。",
    "body": "リクエスト本文。",
    "headers": "HTTPリクエストヘッダー。",
    "user_id": "ユーザーID。",
    "db_path": "旧呼び出し互換のためのDB指定。",
    "e": "発生した例外。",
    "error": "発生した例外。",
}
METHOD_SUMMARIES = {
    "__init__": "クラスを初期化する。",
    "validate_body": "リクエスト本文を検証する。",
    "validate_headers": "リクエストヘッダーを検証する。",
    "main": "リクエストに対応する処理を実行する。",
}
MAIN_STEPS = {
    "BudgetReference": ("予算情報を参照する。", "認証済みユーザーと検索条件を取得する。", "有効な予算を照会する。", "画面用の予算情報を返す。"),
    "NewBudgetRegistration": ("予算情報を新規登録する。", "認証済みユーザーと入力値を取得する。", "対象の予算設定と既存データを確認する。", "予算を登録または更新して結果を返す。"),
    "ReceiptUpdateDelete": ("小票を更新または削除する。", "認証済みユーザーと小票IDを取得する。", "対象小票の所有権と内容を検証する。", "更新または論理削除を実行する。", "結果を返す。"),
    "NewReceiptRegistration": ("小票を新規登録する。", "認証済みユーザーと小票情報を取得する。", "明細と重複を検証する。", "小票IDと登録番号を確定する。", "小票本体と明細を保存する。", "登録結果を返す。"),
    "ReceiptReference": ("条件に一致する小票を参照する。", "認証済みユーザーと検索条件を取得する。", "小票本体と明細を照会する。", "店舗ロゴと画面用項目を補完する。", "一覧を返す。"),
    "AutoInputScheduler": ("有効な自動入力をユーザー別に実行する。", "実行対象の連携先を決める。", "有効な連携設定を照会する。", "連携先ごとにバッチを実行する。", "成功・失敗件数を返す。"),
    "AutoInput_Etc": ("ETC明細を取り込む。", "対象ユーザーと連携設定を確認する。", "ETC明細を取得する。", "未登録明細を小票へ変換する。", "取込結果を返す。"),
    "AutoInput_Belc": ("BELC購入履歴を取り込む。", "対象ユーザーと連携設定を確認する。", "購入履歴を取得する。", "未登録明細を小票へ変換する。", "取込結果を返す。"),
    "AutoInput_Suica": ("Suica利用履歴を取り込む。", "対象ユーザーと連携設定を確認する。", "利用履歴を取得する。", "未登録明細を小票へ変換する。", "取込結果を返す。"),
    "AutoInput_Amazon": ("Amazon購入履歴を取り込む。", "対象ユーザーとログイン状態を確認する。", "購入履歴を取得する。", "未登録明細を小票へ変換する。", "取込結果を返す。"),
    "BaseLambda": ("APIまたはバッチ固有の主処理を定義する。", "共通のリクエスト情報を受け取る。", "実装クラスで固有処理を実行する。", "標準レスポンスを返す。"),
    "BaseValidator": ("バリデーションの主処理を定義する。", "入力値を受け取る。", "実装クラスで検証する。", "検証結果を返す。"),
}


def method_docstring(node: ast.FunctionDef, existing: str) -> str:
    """Preserve existing text and append missing required sections."""
    content = inspect.cleandoc(existing).strip() if existing else ""
    if not content:
        content = METHOD_SUMMARIES.get(node.name, f"{node.name}の処理を実行する。")
    if "Args:" not in content:
        parameters = [arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs if arg.arg not in {"self", "cls"}]
        lines = []
        for arg in parameters:
            annotation = ast.unparse(arg.annotation) if arg.annotation else "Any"
            description = ARG_DESCRIPTIONS.get(arg.arg, f"{arg.arg}の値。")
            lines.append(f"    {arg.arg} ({annotation}): {description}")
        if node.args.vararg:
            lines.append(f"    *{node.args.vararg.arg}: 追加の位置引数。")
        if node.args.kwarg:
            lines.append(f"    **{node.args.kwarg.arg}: 追加のキーワード引数。")
        if not lines:
            lines = ["    None: 引数なし。"]
        section = "Args:\n" + "\n".join(lines)
        if "Raises:" in content:
            content = content.replace("Raises:", section + "\n\nRaises:", 1)
        else:
            content += "\n\n" + section
    if "Returns:" not in content:
        annotation = ast.unparse(node.returns) if node.returns else "Any"
        if node.name == "__init__":
            annotation = "None"
        section = f"Returns:\n    {annotation}: " + ("戻り値なし。" if annotation == "None" else "処理結果。")
        if "Raises:" in content:
            content = content.replace("Raises:", section + "\n\nRaises:", 1)
        else:
            content += "\n\n" + section
    return content


def normalized_source(source: str) -> str:
    """Use AST locations to edit only class method docstrings."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    def offset(line_number: int, byte_column: int) -> int:
        prefix = lines[line_number - 1].encode("utf-8")[:byte_column].decode("utf-8")
        return starts[line_number - 1] + len(prefix)
    edits = []
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for method in cls.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            first = method.body[0]
            old_node = first if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else None
            old = old_node.value.value if old_node else ""
            if old.startswith("\n") and "Args:" in old and "Returns:" in old and (method.name != "main" or ("処理概要:" in old and "処理内容:" in old)):
                continue
            indent = " " * first.col_offset
            if method.name == "main" and cls.name in MAIN_STEPS and "処理概要:" not in old:
                summary, *steps = MAIN_STEPS[cls.name]
                details = inspect.cleandoc(old).strip()
                sections = details[details.find("Args:"):] if "Args:" in details else ""
                old = (
                    "処理概要: " + summary + "\n処理内容:\n"
                    + "\n".join(f"  {index}. {step}" for index, step in enumerate(steps, 1))
                    + ("\n\n" + sections if sections else "")
                )
            content = method_docstring(method, old)
            new = '"""\n' + "\n".join(indent + line if line else "" for line in content.splitlines()) + "\n" + indent + '"""'
            if old_node:
                start = offset(old_node.lineno, old_node.col_offset)
                end = offset(old_node.end_lineno, old_node.end_col_offset)
            else:
                start = starts[first.lineno - 1]
                end = start
                new = indent + new + "\n"
            edits.append((start, end, new))
    for start, end, value in sorted(edits, reverse=True):
        source = source[:start] + value + source[end:]
    return source


def main() -> int:
    """Normalize the API tree or report files needing normalization."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = []
    paths = [path for directory in TARGET_DIRS for path in directory.rglob("*.py")]
    for path in sorted(paths):
        source = path.read_text(encoding="utf-8")
        next_source = normalized_source(source)
        if next_source != source:
            changed.append(path.relative_to(ROOT))
            if not args.check:
                ast.parse(next_source)
                path.write_text(next_source, encoding="utf-8")
    for path in changed:
        print(path)
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
