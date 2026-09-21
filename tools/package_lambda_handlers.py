"""Build one-function Lambda packages without modifying source handlers."""

from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template.yaml"
PACKAGE_ROOT = ROOT / "dist_lambda" / "function"


def main():
    """
    処理概要: SAMの各関数用に固有のハンドラーパッケージを作成する。
    処理内容:
      1. テンプレートに記載されたCodeUriを収集する。
      2. 対応するAPIまたはバッチのハンドラーを検証する。
      3. 生成済みパッケージを入れ替え、各関数に一つだけ配置する。

    Args:
        なし。

    Returns:
        None: 戻り値なし。
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    names = set(re.findall(r"CodeUri: dist_lambda/function/([a-z0-9_]+)", template))
    if not names:
        raise ValueError("No function packages found in SAM template.")

    sources = {}
    for name in names:
        candidates = [ROOT / directory / name / "lambda_handler.py" for directory in ("lambda_api", "lambda_batch")]
        matches = [path for path in candidates if path.is_file()]
        if len(matches) != 1:
            raise ValueError(f"Expected one lambda_handler.py for {name}; found {len(matches)}")
        sources[name] = matches[0]

    if PACKAGE_ROOT.exists():
        shutil.rmtree(PACKAGE_ROOT)
    for name, source in sorted(sources.items()):
        destination = PACKAGE_ROOT / name
        destination.mkdir(parents=True)
        shutil.copy2(source, destination / "lambda_handler.py")
    print(f"Packaged {len(sources)} isolated Lambda handlers.")


if __name__ == "__main__":
    main()
