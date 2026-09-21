"""Keep Lambda log groups aligned with the domain and API layout."""

from pathlib import Path
import re


TEMPLATE = Path(__file__).resolve().parents[1] / "template.yaml"
FUNCTION = re.compile(
    r"(?P<header>^  (?P<logical>[A-Za-z0-9]+Function):\n"
    r"    Type: AWS::Serverless::Function\n"
    r"(?P<condition>    Condition: [A-Za-z0-9]+\n)?"
    r"    Properties:\n"
    r"      FunctionName: home-kakeibo-(?P<name>[a-z0-9-]+)\n"
    r"      Handler: lambda_handler.lambda_handler\n"
    r"      CodeUri: dist_lambda/function/(?P<package>[a-z0-9_]+))",
    re.MULTILINE,
)


def category(name):
    """Return the domain and API category of a deployed function."""
    if name == "auto-input-scheduled":
        return "batch/kakeibo/auto-input"
    if name == "meal-api":
        return "api/meal/recipe-shopping"
    if name == "childcare-api":
        return "api/childcare/family-baby"
    for prefix, group in (
        ("ai-receipt", "receipt/ai"),
        ("recurring-expenses", "receipt/recurring"),
        ("receipt", "receipt/core"),
        ("budget", "budget"),
        ("income", "income"),
        ("auto-linkage", "auto-linkage"),
        ("category", "master/category"),
        ("default-categories", "master/category"),
        ("salary-category", "master/salary-category"),
        ("invoice", "master/invoice"),
        ("supplier-by-invoice", "master/invoice"),
        ("user", "settings/auth"),
        ("app-settings", "settings/app"),
        ("dashboard-layout", "settings/dashboard"),
    ):
        if name.startswith(prefix):
            return f"api/kakeibo/{group}"
    raise ValueError(f"Unclassified Lambda function: {name}")


def main():
    """
    処理概要: Lambdaログを領域・API種別・個別関数で分類する。
    処理内容:
      1. SAMテンプレートの全関数を読み取る。
      2. 各関数に専用ロググループの参照を設定する。
      3. 30日保持のロググループをCloudFormationリソースとして追加する。

    Args:
        なし。

    Returns:
        None: 戻り値なし。
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    if "LoggingConfig:" in template:
        raise ValueError("Template already has logging configuration; review changes manually.")

    groups = []

    def add_configuration(match):
        name = match.group("name")
        log_id = match.group("logical").removesuffix("Function") + "LogGroup"
        log_name = f"/home-kakeibo/{category(name)}/{name}"
        condition = match.group("condition") or ""
        groups.append(
            f"  {log_id}:\n"
            f"    Type: AWS::Logs::LogGroup\n"
            f"{condition}"
            f"    Properties:\n"
            f"      LogGroupName: {log_name}\n"
            f"      RetentionInDays: 30\n"
        )
        return match.group("header") + f"\n      LoggingConfig:\n        LogFormat: JSON\n        LogGroup: !Ref {log_id}"

    template, count = FUNCTION.subn(add_configuration, template)
    if count != 56:
        raise ValueError(f"Expected 56 Lambda functions; found {count}.")
    template = template.replace("\nOutputs:\n", "\n" + "".join(groups) + "\nOutputs:\n", 1)
    TEMPLATE.write_text(template, encoding="utf-8")
    print(f"Configured {count} categorized CloudWatch log groups.")


if __name__ == "__main__":
    main()
