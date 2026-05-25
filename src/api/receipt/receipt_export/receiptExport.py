# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import io
import os
import uuid
from datetime import datetime
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


class ReceiptExportService:
    """レシート検索結果をExcelまたはPDFとして出力するサービス。"""

    def __init__(self):
        self.store = {}

    def prepare(self, request):
        """出力対象データを一時保存し、ダウンロードページURLを返す。"""
        export_type = self.text((request or {}).get("type")).lower()
        if export_type not in ("excel", "pdf"):
            return {"statusCode": 400, "body": {"errorMessage": "出力形式が不正です。"}}

        rows = self.normalize_rows((request or {}).get("rows") or [])
        if not rows:
            return {"statusCode": 400, "body": {"errorMessage": "出力対象のデータがありません。"}}

        token = uuid.uuid4().hex
        self.store[token] = {
            "type": export_type,
            "rows": rows,
            "createdAt": datetime.now(),
        }
        return {"statusCode": 200, "body": {"url": f"/export/receipt/page/{token}"}}

    def page_html(self, token):
        """ブラウザでダウンロードを開始するための中間HTMLを作成する。"""
        if token not in self.store:
            return None
        return f"""
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8">
    <title>レシート出力</title>
    <style>
      body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: "Yu Gothic", "Meiryo", sans-serif; background: #f8fafc; color: #111827; }}
      main {{ width: min(520px, calc(100vw - 40px)); padding: 32px; border: 1px solid #dbeafe; border-radius: 8px; background: #fff; box-shadow: 0 18px 45px rgba(15, 23, 42, .10); }}
      h1 {{ margin: 0 0 12px; font-size: 22px; }}
      p {{ margin: 0 0 20px; color: #475569; line-height: 1.7; }}
      a {{ color: #1d4ed8; font-weight: 700; }}
    </style>
  </head>
  <body>
    <main>
      <h1>ダウンロードを開始しています</h1>
      <p>ファイルの保存が始まらない場合は、下のリンクをクリックしてください。</p>
      <a id="downloadLink" href="/export/receipt/file/{token}">ファイルをダウンロード</a>
    </main>
    <script>
      window.addEventListener("load", () => document.getElementById("downloadLink").click());
    </script>
  </body>
</html>
"""

    def build_file(self, token):
        """保存済みトークンから出力ファイル本体とヘッダ情報を作る。"""
        export_data = self.store.get(token)
        if not export_data:
            return None

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        if export_data["type"] == "excel":
            filename = f"レシート検索結果_{now}.xlsx"
            return {
                "content": self.build_excel(export_data["rows"]),
                "filename": filename,
                "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }

        filename = f"レシート検索結果_{now}.pdf"
        return {
            "content": self.build_pdf(export_data["rows"]),
            "filename": filename,
            "media_type": "application/pdf",
        }

    def attachment_headers(self, filename):
        """日本語ファイル名を含むダウンロードヘッダを作成する。"""
        fallback = "receipt_report" + os.path.splitext(filename)[1]
        return {
            "Content-Disposition": f"attachment; filename={fallback}; filename*=UTF-8''{quote(filename)}"
        }

    def normalize_rows(self, rows):
        """画面から渡された検索結果を出力用の安定した行形式へ変換する。"""
        normalized = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            normalized.append({
                "receiptDate": self.text(row.get("receiptDate")),
                "receiptTime": self.text(row.get("receiptTime")),
                "invoiceRegistrationNumber": self.text(row.get("invoiceRegistrationNumber")),
                "supplierName": self.text(row.get("supplierName")),
                "category1": self.text(row.get("category1")),
                "category2": self.text(row.get("category2")),
                "itemName": self.text(row.get("itemName")),
                "quantity": self.number(row.get("quantity")),
                "unitPrice": self.number(row.get("unitPrice")),
                "taxRate": self.number(row.get("taxRate")),
                "totalPrice": self.number(row.get("totalPrice")),
            })
        return normalized

    def build_excel(self, rows):
        """明細、概要、分類集計、月別集計を含むExcelファイルを作成する。"""
        workbook = Workbook()
        detail = workbook.active
        detail.title = "明細"
        detail.append(["日付", "時刻", "登録番号", "店舗", "分類", "小分類", "商品名", "数量", "単価", "税率", "金額"])
        for row in rows:
            detail.append([
                row["receiptDate"],
                row["receiptTime"],
                row["invoiceRegistrationNumber"],
                row["supplierName"],
                row["category1"],
                row["category2"],
                row["itemName"],
                row["quantity"],
                row["unitPrice"],
                self.format_tax_rate(row["taxRate"]),
                row["totalPrice"],
            ])
        self.style_sheet(detail, [14, 10, 20, 24, 16, 18, 34, 10, 12, 10, 14])
        for cell in detail["I"][1:] + detail["K"][1:]:
            cell.number_format = '#,##0"円"'

        total, category_totals, month_totals = self.summary(rows)
        summary = workbook.create_sheet("概要")
        summary.append(["項目", "値"])
        summary.append(["明細件数", len(rows)])
        summary.append(["合計金額", total])
        summary.append(["分類数", len(category_totals)])
        summary.append(["出力日時", datetime.now().strftime("%Y/%m/%d %H:%M")])
        self.style_sheet(summary, [20, 24])
        summary["B3"].number_format = '#,##0"円"'

        by_category = workbook.create_sheet("分類集計")
        by_category.append(["分類", "金額"])
        for category, amount in sorted(category_totals.items(), key=lambda item: item[1], reverse=True):
            by_category.append([category, amount])
        self.style_sheet(by_category, [24, 16])
        for cell in by_category["B"][1:]:
            cell.number_format = '#,##0"円"'

        by_month = workbook.create_sheet("月別集計")
        by_month.append(["月", "金額"])
        for month, amount in sorted(month_totals.items()):
            by_month.append([month, amount])
        self.style_sheet(by_month, [16, 16])
        for cell in by_month["B"][1:]:
            cell.number_format = '#,##0"円"'

        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()

    def style_sheet(self, sheet, widths):
        """Excelシートのヘッダ、罫線、列幅を整える。"""
        header_fill = PatternFill("solid", fgColor="1F4E78")
        header_font = Font(name="Yu Gothic", bold=True, color="FFFFFF")
        body_font = Font(name="Yu Gothic", color="1F2937")
        thin = Side(style="thin", color="D9E2F3")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[chr(64 + index)].width = width
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for row in sheet.iter_rows():
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if cell.row == 1:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.font = body_font
                    if cell.row % 2 == 0:
                        cell.fill = PatternFill("solid", fgColor="F8FAFC")

    def build_pdf(self, rows):
        """検索結果を簡易PDFへ変換する。"""
        lines = ["レシート検索結果レポート", f"出力日時: {datetime.now().strftime('%Y/%m/%d %H:%M')}"]
        total, _, _ = self.summary(rows)
        lines.extend([f"明細件数: {len(rows)}", f"合計金額: {self.format_yen(total)}", ""])
        for row in rows:
            lines.append(
                f"{row['receiptDate']} {row['supplierName']} {row['itemName']} {self.format_yen(row['totalPrice'])}"
            )
        return self.simple_pdf(lines)

    def simple_pdf(self, lines):
        """標準フォントだけで読める最小構成のPDFを作成する。"""
        page_w, page_h = 595, 842
        parts = []
        y = page_h - 48
        for line in lines[:42]:
            parts.append(f"BT /F1 10 Tf 1 0 0 1 40 {y} Tm {self.pdf_hex(line)} Tj ET")
            y -= 18
        stream = "\n".join(parts).encode("utf-8")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [6 0 R] /Count 1 >>",
            b"<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiKakuGo-W5 /Encoding /UniJIS-UCS2-H /DescendantFonts [4 0 R] >>",
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiKakuGo-W5 /CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 6 >> /DW 1000 >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w} {page_h}] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>".encode("ascii"),
        ]
        output = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(output))
            output += f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        xref = len(output)
        output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
        for offset in offsets[1:]:
            output += f"{offset:010d} 00000 n \n".encode("ascii")
        output += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
        return output

    def summary(self, rows):
        """出力用データから総額、分類別、月別の集計を作る。"""
        total = sum(self.number(row.get("totalPrice")) for row in rows)
        category_totals = {}
        month_totals = {}
        for row in rows:
            category = row.get("category1") or "未分類"
            category_totals[category] = category_totals.get(category, 0) + self.number(row.get("totalPrice"))
            month = (row.get("receiptDate") or "不明")[:7] or "不明"
            month_totals[month] = month_totals.get(month, 0) + self.number(row.get("totalPrice"))
        return total, category_totals, month_totals

    def pdf_hex(self, text):
        """PDFの日本語文字列として埋め込める16進文字列へ変換する。"""
        return "<" + self.text(text).encode("utf-16-be").hex().upper() + ">"

    def text(self, value):
        """Noneを空文字に寄せて出力用文字列へ変換する。"""
        return "" if value is None else str(value).strip()

    def number(self, value):
        """出力集計で扱う数値を安全にfloatへ変換する。"""
        try:
            if value is None or value == "":
                return 0
            return float(value)
        except (TypeError, ValueError):
            return 0

    def format_yen(self, value):
        """円表記用に小数を丸めてカンマ付き文字列へ変換する。"""
        return f"{int(round(self.number(value))):,}円"

    def format_tax_rate(self, value):
        """税率を百分率表記へ変換する。"""
        rate = self.number(value)
        if rate <= 0:
            return ""
        return f"{round(rate * 100):g}%"
