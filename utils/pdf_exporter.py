# -*- coding: utf-8 -*-
"""
PDF导出模块
功能：生成专业格式的PDF报价单
"""

import os
import io
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class PDFExporter:
    """PDF导出器"""

    def __init__(self, company_info: Dict = None):
        """
        初始化PDF导出器

        Args:
            company_info: 公司信息字典
                - name: 公司名称
                - logo_path: Logo路径
                - address: 地址
                - phone: 电话
                - email: 邮箱
        """
        self.company_info = company_info or {
            'name': '赛正慧采商城',
            'address': '',
            'phone': '',
            'email': ''
        }
        self.reportlab_available = self._check_reportlab()
        self.weasyprint_available = self._check_weasyprint()

    def _check_reportlab(self) -> bool:
        """检查reportlab是否可用"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
            return True
        except ImportError:
            return False

    def _check_weasyprint(self) -> bool:
        """检查weasyprint是否可用"""
        try:
            from weasyprint import HTML, CSS
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        """检查PDF导出是否可用"""
        return self.reportlab_available or self.weasyprint_available

    def get_available_method(self) -> str:
        """获取可用的导出方法"""
        if self.weasyprint_available:
            return 'weasyprint'
        elif self.reportlab_available:
            return 'reportlab'
        return 'none'

    def export_quote_pdf(self, results: List[Dict], output_path: str,
                         customer_name: str = '',
                         quote_number: str = None,
                         watermark: str = None,
                         include_signature: bool = True) -> str:
        """
        导出报价单PDF

        Args:
            results: 匹配结果列表
            output_path: 输出路径
            customer_name: 客户名称
            quote_number: 报价单号
            watermark: 水印文字
            include_signature: 是否包含签名区域

        Returns:
            输出文件路径
        """
        if self.weasyprint_available:
            return self._export_with_weasyprint(
                results, output_path, customer_name, quote_number, watermark, include_signature
            )
        elif self.reportlab_available:
            return self._export_with_reportlab(
                results, output_path, customer_name, quote_number, watermark, include_signature
            )
        else:
            raise RuntimeError("PDF导出功能不可用，请安装reportlab或weasyprint")

    def _export_with_weasyprint(self, results: List[Dict], output_path: str,
                                  customer_name: str, quote_number: str,
                                  watermark: str, include_signature: bool) -> str:
        """使用WeasyPrint导出PDF（HTML转PDF，样式更丰富）"""
        from weasyprint import HTML, CSS

        # 生成报价单号
        if not quote_number:
            quote_number = f"QT{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 计算汇总数据
        total_items = len(results)
        matched_items = sum(1 for r in results if r.get('action') == 'select')
        total_amount = sum(
            (r.get('query_item', {}).get('quantity', 0) or 0) *
            (r.get('selected_product', {}).get('product', {}).get('market_price', 0) or 0)
            for r in results if r.get('action') == 'select'
        )

        # 生成HTML内容
        html_content = self._generate_quote_html(
            results, customer_name, quote_number, total_items, matched_items, total_amount,
            watermark, include_signature
        )

        # CSS样式
        css_content = """
        @page {
            size: A4;
            margin: 1.5cm;
            @bottom-center {
                content: counter(page) " / " counter(pages);
                font-size: 9pt;
                color: #666;
            }
        }

        body {
            font-family: "Microsoft YaHei", "SimSun", sans-serif;
            font-size: 10pt;
            color: #333;
            line-height: 1.4;
        }

        .header {
            text-align: center;
            border-bottom: 2px solid #6366f1;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }

        .company-name {
            font-size: 22pt;
            font-weight: bold;
            color: #6366f1;
            margin-bottom: 5px;
        }

        .doc-title {
            font-size: 16pt;
            color: #333;
            margin-top: 10px;
        }

        .info-section {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
            font-size: 10pt;
        }

        .info-box {
            width: 48%;
        }

        .info-label {
            color: #666;
            margin-right: 5px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }

        th {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            color: white;
            padding: 10px 8px;
            text-align: left;
            font-size: 10pt;
        }

        td {
            padding: 8px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 9pt;
        }

        tr:nth-child(even) {
            background: #f8fafc;
        }

        tr.matched {
            background: #f0fdf4;
        }

        tr.unmatched {
            background: #fef2f2;
        }

        .summary {
            margin-top: 20px;
            padding: 15px;
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }

        .summary-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }

        .total-amount {
            font-size: 14pt;
            font-weight: bold;
            color: #6366f1;
        }

        .signature-section {
            margin-top: 40px;
            display: flex;
            justify-content: space-between;
        }

        .signature-box {
            width: 45%;
            border-top: 1px solid #333;
            padding-top: 10px;
            margin-top: 60px;
            text-align: center;
        }

        .watermark {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(-45deg);
            font-size: 60pt;
            color: rgba(99, 102, 241, 0.1);
            pointer-events: none;
            white-space: nowrap;
        }

        .footer {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            text-align: center;
            font-size: 8pt;
            color: #999;
            padding: 10px;
            border-top: 1px solid #e2e8f0;
        }
        """

        # 创建PDF
        html = HTML(string=html_content)
        css = CSS(string=css_content)
        html.write_pdf(output_path, stylesheets=[css])

        return output_path

    def _generate_quote_html(self, results: List[Dict], customer_name: str,
                               quote_number: str, total_items: int, matched_items: int,
                               total_amount: float, watermark: str, include_signature: bool) -> str:
        """生成报价单HTML"""

        watermark_html = f'<div class="watermark">{watermark}</div>' if watermark else ''

        # 表格行
        rows_html = ''
        for i, result in enumerate(results, 1):
            query = result.get('query_item', {})
            action = result.get('action', '')

            row_class = 'matched' if action == 'select' else ('unmatched' if action == 'no_match' else '')

            if action == 'select' and result.get('selected_product'):
                product = result['selected_product'].get('product', {})
                product_name = product.get('name', '')
                product_code = product.get('code', '')
                price = product.get('market_price', 0) or 0
                brand = product.get('brand', '')
            else:
                product_name = '-'
                product_code = '-'
                price = 0
                brand = '-'

            quantity = query.get('quantity', 0) or 0
            subtotal = quantity * price

            rows_html += f'''
            <tr class="{row_class}">
                <td style="text-align: center;">{i}</td>
                <td>{query.get('name', '')}</td>
                <td style="text-align: center;">{quantity}</td>
                <td style="text-align: center;">{query.get('unit', '')}</td>
                <td>{product_name}</td>
                <td>{product_code}</td>
                <td style="text-align: right;">¥{price:.2f}</td>
                <td style="text-align: right;">¥{subtotal:.2f}</td>
            </tr>
            '''

        signature_html = ''
        if include_signature:
            signature_html = '''
            <div class="signature-section">
                <div class="signature-box">
                    <div>客户签字：_______________</div>
                    <div style="font-size: 8pt; color: #999; margin-top: 5px;">日期：______年______月______日</div>
                </div>
                <div class="signature-box">
                    <div>报价人签字：_______________</div>
                    <div style="font-size: 8pt; color: #999; margin-top: 5px;">日期：______年______月______日</div>
                </div>
            </div>
            '''

        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body>
            {watermark_html}

            <div class="header">
                <div class="company-name">{self.company_info.get('name', '赛正慧采商城')}</div>
                <div class="doc-title">报 价 单</div>
            </div>

            <div class="info-section">
                <div class="info-box">
                    <div><span class="info-label">报价单号：</span>{quote_number}</div>
                    <div><span class="info-label">报价日期：</span>{datetime.now().strftime('%Y年%m月%d日')}</div>
                    <div><span class="info-label">客户名称：</span>{customer_name or '_______________'}</div>
                </div>
                <div class="info-box" style="text-align: right;">
                    <div><span class="info-label">联系电话：</span>{self.company_info.get('phone', '')}</div>
                    <div><span class="info-label">电子邮箱：</span>{self.company_info.get('email', '')}</div>
                    <div><span class="info-label">有效期：</span>30天</div>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th style="width: 5%;">序号</th>
                        <th style="width: 20%;">需求产品</th>
                        <th style="width: 8%;">数量</th>
                        <th style="width: 6%;">单位</th>
                        <th style="width: 22%;">匹配商品</th>
                        <th style="width: 12%;">商品编码</th>
                        <th style="width: 10%;">单价</th>
                        <th style="width: 12%;">金额</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>

            <div class="summary">
                <div class="summary-row">
                    <span>总项目数：<strong>{total_items}</strong> 项</span>
                    <span>已匹配：<strong>{matched_items}</strong> 项</span>
                    <span>匹配率：<strong>{(matched_items/total_items*100) if total_items > 0 else 0:.1f}%</strong></span>
                </div>
                <div class="summary-row" style="margin-top: 10px;">
                    <span class="total-amount">合计金额：¥{total_amount:,.2f}</span>
                </div>
            </div>

            {signature_html}

            <div class="footer">
                {self.company_info.get('name', '')} | {self.company_info.get('address', '')}
            </div>
        </body>
        </html>
        '''

        return html

    def _export_with_reportlab(self, results: List[Dict], output_path: str,
                                 customer_name: str, quote_number: str,
                                 watermark: str, include_signature: bool) -> str:
        """使用ReportLab导出PDF（基础方案）"""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        # 注册中文字体
        try:
            pdfmetrics.registerFont(TTFont('SimSun', 'simsun.ttc'))
            font_name = 'SimSun'
        except:
            font_name = 'Helvetica'

        # 创建PDF文档
        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontName=font_name,
            fontSize=18,
            alignment=1,
            spaceAfter=20
        )

        elements = []

        # 标题
        elements.append(Paragraph('报价单', title_style))
        elements.append(Spacer(1, 0.5*cm))

        # 信息区
        if not quote_number:
            quote_number = f"QT{datetime.now().strftime('%Y%m%d%H%M%S')}"

        info_style = ParagraphStyle('Info', fontName=font_name, fontSize=10)
        elements.append(Paragraph(f'报价单号：{quote_number}', info_style))
        elements.append(Paragraph(f'报价日期：{datetime.now().strftime("%Y年%m月%d日")}', info_style))
        if customer_name:
            elements.append(Paragraph(f'客户名称：{customer_name}', info_style))
        elements.append(Spacer(1, 0.5*cm))

        # 表格数据
        table_data = [['序号', '需求产品', '数量', '单位', '匹配商品', '单价', '金额']]

        total_amount = 0
        for i, result in enumerate(results, 1):
            query = result.get('query_item', {})
            if result.get('action') == 'select' and result.get('selected_product'):
                product = result['selected_product'].get('product', {})
                product_name = product.get('name', '')[:20]
                price = product.get('market_price', 0) or 0
            else:
                product_name = '-'
                price = 0

            quantity = query.get('quantity', 0) or 0
            subtotal = quantity * price
            total_amount += subtotal

            table_data.append([
                str(i),
                str(query.get('name', ''))[:15],
                str(quantity),
                str(query.get('unit', '')),
                product_name,
                f'¥{price:.2f}',
                f'¥{subtotal:.2f}'
            ])

        # 合计行
        table_data.append(['', '', '', '', '', '合计：', f'¥{total_amount:,.2f}'])

        # 创建表格
        table = Table(table_data, colWidths=[1*cm, 4*cm, 1.5*cm, 1.5*cm, 4*cm, 2*cm, 2.5*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
            ('FONTNAME', (0, -1), (-1, -1), font_name),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
        ]))

        elements.append(table)

        # 构建PDF
        doc.build(elements)

        return output_path


def create_pdf_exporter(company_info: Dict = None) -> PDFExporter:
    """创建PDF导出器实例"""
    return PDFExporter(company_info)