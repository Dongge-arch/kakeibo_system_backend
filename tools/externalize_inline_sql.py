"""Move static database statements to adjacent SQL files.

Run with a development environment that has sqlparse installed. Dynamic SQL
expressions are intentionally left for manual review.
"""

import ast
from pathlib import Path
import re
import textwrap

import sqlparse


ROOT = Path(__file__).resolve().parents[1]
QUERY = re.compile(r"^(SELECT|INSERT|UPDATE|DELETE|WITH)\b", re.IGNORECASE)
PLACEHOLDER = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")


def query_name(sql):
    """Give a static query a readable operation-and-table filename."""
    normalized = sql.strip()
    verb = QUERY.match(normalized).group(1).upper()
    if verb == "INSERT":
        pattern = r"\bINTO\s+([A-Za-z_][A-Za-z_0-9.]*)"
    elif verb == "UPDATE":
        pattern = r"\bUPDATE\s+([A-Za-z_][A-Za-z_0-9.]*)"
    else:
        pattern = r"\bFROM\s+([A-Za-z_][A-Za-z_0-9.]*)"
    table = re.search(pattern, normalized, re.IGNORECASE)
    name = table.group(1).replace(".", "_").upper() if table else "QUERY"
    return f"{verb}_{name}"


def main():
    """
    処理概要: API・バッチ内の固定SQLを外部ファイルへ移動する。
    処理内容:
      1. Pythonの構文木からDB呼び出しの固定SQLを検出する。
      2. SQLキーワード・識別子・パラメータ名を大文字に整える。
      3. APIごとのsqlディレクトリへ保存し、read_sql呼び出しに置換する。

    Args:
        なし。

    Returns:
        None: 戻り値なし。
    """
    total = 0
    for root in (ROOT / "src" / "api", ROOT / "src" / "batch", ROOT / "src" / "common" / "base"):
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            lines = source.splitlines(keepends=True)
            offsets = [0]
            for line in lines:
                offsets.append(offsets[-1] + len(line.encode("utf-8")))

            edits = []
            sql_dir = path.parent / "sql"
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"select", "insert", "update", "execute", "execute_many"} or not node.args:
                    continue
                receiver = node.func.value
                if not (
                    isinstance(receiver, ast.Attribute)
                    and isinstance(receiver.value, ast.Name)
                    and receiver.value.id == "self"
                    and receiver.attr == "database"
                ):
                    continue
                first = node.args[0]
                if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                    continue
                raw_sql = textwrap.dedent(first.value).strip()
                if not QUERY.match(raw_sql):
                    continue
                # sqlparse preserves quoted string values while normalizing SQL identifiers.
                sql = sqlparse.format(raw_sql, keyword_case="upper", identifier_case="upper").strip()
                sql = PLACEHOLDER.sub(lambda match: f"%({match.group(1).upper()})s", sql)
                sql_dir.mkdir(exist_ok=True)
                base_name = query_name(sql)
                name = base_name
                counter = 2
                while (sql_dir / f"{name}.sql").exists():
                    name = f"{base_name}_{counter:02d}"
                    counter += 1
                (sql_dir / f"{name}.sql").write_text(sql + "\n", encoding="utf-8")
                start = offsets[first.lineno - 1] + first.col_offset
                end = offsets[first.end_lineno - 1] + first.end_col_offset
                edits.append((start, end, f'self.database.read_sql("{name}", location=__file__)'.encode("utf-8")))

            if edits:
                content = source.encode("utf-8")
                for start, end, replacement in sorted(edits, reverse=True):
                    content = content[:start] + replacement + content[end:]
                path.write_bytes(content)
                total += len(edits)
    normalized = 0
    for root in (ROOT / "src" / "api", ROOT / "src" / "batch", ROOT / "src" / "common" / "base"):
        for path in root.rglob("*.sql"):
            original = path.read_text(encoding="utf-8")
            sql = sqlparse.format(original, keyword_case="upper", identifier_case="upper").strip()
            sql = PLACEHOLDER.sub(lambda match: f"%({match.group(1).upper()})s", sql) + "\n"
            if sql != original:
                path.write_text(sql, encoding="utf-8")
                normalized += 1
    print(f"Externalized {total} static statements; normalized {normalized} SQL files.")


if __name__ == "__main__":
    main()
