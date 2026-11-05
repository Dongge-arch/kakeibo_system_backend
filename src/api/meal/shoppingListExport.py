"""買い物リストのPDF・Excel出力 API。"""

import base64
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from src.api.meal.mealBase import MealBase, RecipeValidationError
from src.common.const.datetime import TIME_ZONE_JST
from src.common.functions.response import response


PDF_FONT = "HeiseiKakuGo-W5"


def format_amount(value, unit_label):
    """数量と表示単位を買い物リスト向けに整形する。"""
    if value is None:
        return "適量"
    number = int(value) if float(value).is_integer() else value
    return f"{number}{unit_label}"


class ShoppingListExport(MealBase):
    """買い物リストのダウンロードデータを生成する。"""

    def main(self, request_dict):
        """選択内容を検証し、PDFまたはExcelをBase64で返す。"""
        user_id = self.require_verified_user_id(request_dict)
        body = request_dict.get("body") or {}
        try:
            manual_items = self.normalize_manual_items(body.get("manualItems") or [])
            selections = self.normalize_selections(
                body.get("selections") or [],
                allow_empty=bool(manual_items),
            )
        except RecipeValidationError as error:
            return response(400, {"errorMessage": str(error)})
        file_format = str(body.get("format") or "").lower()
        layout = str(body.get("layout") or "desktop").lower()
        if file_format not in {"pdf", "xlsx"} or layout not in {"mobile", "desktop"}:
            return response(400, {"errorMessage": "出力形式が正しくありません。"})
        preview = self.build_shopping_preview(user_id, selections)
        if preview is None:
            return response(404, {"errorMessage": "選択したレシピが見つかりません。"})
        preview["manualItems"] = manual_items

        timestamp = datetime.now(ZoneInfo(TIME_ZONE_JST)).strftime("%Y%m%d_%H%M")
        if file_format == "pdf":
            content = self.build_pdf(preview, layout)
            filename = f"買い物リスト_{timestamp}.pdf"
            media_type = "application/pdf"
        else:
            content = self.build_xlsx(preview)
            filename = f"買い物リスト_{timestamp}.xlsx"
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response(200, {
            "filename": filename,
            "mediaType": media_type,
            "contentBase64": base64.b64encode(content).decode("ascii"),
        })

    @staticmethod
    def build_pdf(preview, layout):
        """日本語対応の買い物リストPDFを作成する。"""
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, A6
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        try:
            pdfmetrics.getFont(PDF_FONT)
        except KeyError:
            pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT))
        buffer = BytesIO()
        mobile = layout == "mobile"
        page_size = A6 if mobile else A4
        margin = 10 * mm if mobile else 16 * mm
        document = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            rightMargin=margin,
            leftMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title="買い物リスト",
            author="Home Kakeibo System",
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "JapaneseTitle",
            parent=styles["Title"],
            fontName=PDF_FONT,
            fontSize=17 if mobile else 22,
            leading=22 if mobile else 28,
            textColor=colors.HexColor("#173F3A"),
            alignment=TA_LEFT,
        )
        heading_style = ParagraphStyle(
            "JapaneseHeading",
            parent=styles["Heading2"],
            fontName=PDF_FONT,
            fontSize=11 if mobile else 13,
            leading=15,
            textColor=colors.HexColor("#173F3A"),
            spaceBefore=7,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "JapaneseBody",
            parent=styles["BodyText"],
            fontName=PDF_FONT,
            fontSize=8 if mobile else 9,
            leading=12,
            textColor=colors.HexColor("#243532"),
        )
        story = [
            Paragraph("買い物リスト", title_style),
            Paragraph(
                f"作成日時：{datetime.now(ZoneInfo(TIME_ZONE_JST)).strftime('%Y/%m/%d %H:%M')}",
                body_style,
            ),
            Spacer(1, 5 * mm),
        ]
        for group in preview["materialGroups"]:
            story.append(Paragraph(group["category"], heading_style))
            rows = [
                [
                    Paragraph(f"[ ] {item['name']}", body_style),
                    Paragraph(format_amount(item["purchaseAmount"], item["unitLabel"]), body_style),
                ]
                for item in group["items"]
            ]
            table = Table(rows, colWidths=[page_size[0] - margin * 2 - 28 * mm, 28 * mm])
            table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E3E0")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ]))
            story.append(table)
        if preview.get("manualItems"):
            story.append(Paragraph("追加した買い物", heading_style))
            rows = [
                [Paragraph(f"[ ] {item['name']}", body_style), Paragraph(item.get("quantity") or "", body_style)]
                for item in preview["manualItems"]
            ]
            story.append(Table(rows, colWidths=[page_size[0] - margin * 2 - 28 * mm, 28 * mm]))
        story.extend([PageBreak(), Paragraph("調味料・在庫確認", title_style)])
        story.append(Paragraph("分量は表示していません。在庫の有無だけをご確認ください。", body_style))
        for seasoning in preview["seasonings"]:
            detail = "、".join(
                source["recipeName"] + (f"／{source['usage']}" if source["usage"] else "")
                for source in seasoning["sources"]
            )
            story.append(Paragraph(f"[ ] {seasoning['name']}　〈{detail}〉", body_style))
            story.append(Spacer(1, 2 * mm))
        document.build(story)
        return buffer.getvalue()

    @staticmethod
    def build_xlsx(preview):
        """編集しやすいExcel形式の買い物リストを作成する。"""
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        workbook = Workbook()
        material_sheet = workbook.active
        material_sheet.title = "買い物リスト"
        seasoning_sheet = workbook.create_sheet("調味料・在庫確認")
        recipe_sheet = workbook.create_sheet("選択したレシピ")
        header_fill = PatternFill("solid", fgColor="1F6B61")
        white_font = Font(color="FFFFFF", bold=True)
        thin_border = Border(bottom=Side(style="thin", color="D8E3E0"))

        material_sheet.append(["購入済み", "カテゴリ", "食材", "購入目安", "参照レシピ"])
        for cell in material_sheet[1]:
            cell.fill = header_fill
            cell.font = white_font
        for group in preview["materialGroups"]:
            for item in group["items"]:
                material_sheet.append([
                    "□",
                    group["category"],
                    item["name"],
                    format_amount(item["purchaseAmount"], item["unitLabel"]),
                    "、".join(source["recipeName"] for source in item["sources"]),
                ])
        for item in preview.get("manualItems") or []:
            material_sheet.append(["□", item.get("category") or "その他", item["name"], item.get("quantity") or "", "手動追加"])
        for column, width in {"A": 12, "B": 16, "C": 26, "D": 16, "E": 42}.items():
            material_sheet.column_dimensions[column].width = width
        material_sheet.freeze_panes = "A2"

        seasoning_sheet.append(["在庫あり", "調味料", "レシピ", "用途"])
        for cell in seasoning_sheet[1]:
            cell.fill = header_fill
            cell.font = white_font
        for item in preview["seasonings"]:
            recipe_names = list(dict.fromkeys(source["recipeName"] for source in item["sources"]))
            usages = list(dict.fromkeys(source["usage"] for source in item["sources"] if source["usage"]))
            seasoning_sheet.append(["□", item["name"], "、".join(recipe_names), "、".join(usages)])
        for column, width in {"A": 12, "B": 26, "C": 34, "D": 20}.items():
            seasoning_sheet.column_dimensions[column].width = width
        seasoning_sheet.freeze_panes = "A2"

        recipe_sheet.append(["レシピ", "人数", "作る回数"])
        for cell in recipe_sheet[1]:
            cell.fill = header_fill
            cell.font = white_font
        for item in preview["selections"]:
            recipe_sheet.append([item["recipeName"], item["targetServings"], item["cookCount"]])
        for column, width in {"A": 42, "B": 12, "C": 14}.items():
            recipe_sheet.column_dimensions[column].width = width

        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    cell.alignment = Alignment(vertical="center")
                    cell.border = thin_border
            for cell in sheet[1]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            sheet.auto_filter.ref = sheet.dimensions
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()
