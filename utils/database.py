# -*- coding: utf-8 -*-
"""
数据库模块 - 报价历史记录
使用 SQLite 存储
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional


class QuoteHistoryDB:
    """报价历史记录数据库"""

    def __init__(self, db_path: str = 'data/quote_history.db'):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_match_feedback_columns(self, cursor: sqlite3.Cursor):
        cursor.execute('PRAGMA table_info(match_feedback)')
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {
            'created_at': "ALTER TABLE match_feedback ADD COLUMN created_at TEXT NOT NULL DEFAULT ''",
            'source_type': "ALTER TABLE match_feedback ADD COLUMN source_type TEXT",
            'template_name': "ALTER TABLE match_feedback ADD COLUMN template_name TEXT",
            'template_hit': "ALTER TABLE match_feedback ADD COLUMN template_hit INTEGER DEFAULT 0",
            'action': "ALTER TABLE match_feedback ADD COLUMN action TEXT",
            'original_name': "ALTER TABLE match_feedback ADD COLUMN original_name TEXT",
            'original_spec': "ALTER TABLE match_feedback ADD COLUMN original_spec TEXT",
            'original_unit': "ALTER TABLE match_feedback ADD COLUMN original_unit TEXT",
            'normalized_name': "ALTER TABLE match_feedback ADD COLUMN normalized_name TEXT",
            'normalized_spec': "ALTER TABLE match_feedback ADD COLUMN normalized_spec TEXT",
            'normalized_unit': "ALTER TABLE match_feedback ADD COLUMN normalized_unit TEXT",
            'selected_product_code': "ALTER TABLE match_feedback ADD COLUMN selected_product_code TEXT",
            'selected_product_name': "ALTER TABLE match_feedback ADD COLUMN selected_product_name TEXT",
            'top_candidate_code': "ALTER TABLE match_feedback ADD COLUMN top_candidate_code TEXT",
            'top_candidate_name': "ALTER TABLE match_feedback ADD COLUMN top_candidate_name TEXT",
            'top_candidate_score': "ALTER TABLE match_feedback ADD COLUMN top_candidate_score REAL DEFAULT 0",
            'top_candidate_rank': "ALTER TABLE match_feedback ADD COLUMN top_candidate_rank INTEGER DEFAULT 0",
            'selected_rank': "ALTER TABLE match_feedback ADD COLUMN selected_rank INTEGER DEFAULT 0",
            'selected_score': "ALTER TABLE match_feedback ADD COLUMN selected_score REAL DEFAULT 0",
            'with_product_image': "ALTER TABLE match_feedback ADD COLUMN with_product_image INTEGER DEFAULT 0",
            'ocr_confidence': "ALTER TABLE match_feedback ADD COLUMN ocr_confidence REAL DEFAULT 0",
            'query_signature': "ALTER TABLE match_feedback ADD COLUMN query_signature TEXT",
            'feedback_weight': "ALTER TABLE match_feedback ADD COLUMN feedback_weight REAL DEFAULT 1",
            'mapping_signature': "ALTER TABLE match_feedback ADD COLUMN mapping_signature TEXT",
            'mapping_changed': "ALTER TABLE match_feedback ADD COLUMN mapping_changed INTEGER DEFAULT 0"
        }
        for column, statement in expected_columns.items():
            if column not in columns:
                cursor.execute(statement)

    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quote_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                customer_name TEXT,
                quote_file TEXT,
                total_items INTEGER DEFAULT 0,
                matched_items INTEGER DEFAULT 0,
                total_amount REAL DEFAULT 0,
                export_file TEXT,
                remark TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quote_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_id INTEGER NOT NULL,
                item_name TEXT,
                item_quantity REAL,
                item_unit TEXT,
                item_price REAL,
                budget_price REAL,
                product_name TEXT,
                product_code TEXT,
                supplier TEXT,
                match_score REAL,
                FOREIGN KEY (quote_id) REFERENCES quote_history(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_type TEXT,
                template_name TEXT,
                template_hit INTEGER DEFAULT 0,
                action TEXT,
                original_name TEXT,
                original_spec TEXT,
                original_unit TEXT,
                normalized_name TEXT,
                normalized_spec TEXT,
                normalized_unit TEXT,
                selected_product_code TEXT,
                selected_product_name TEXT,
                top_candidate_code TEXT,
                top_candidate_name TEXT,
                top_candidate_score REAL DEFAULT 0,
                top_candidate_rank INTEGER DEFAULT 0,
                selected_rank INTEGER DEFAULT 0,
                selected_score REAL DEFAULT 0,
                with_product_image INTEGER DEFAULT 0,
                ocr_confidence REAL DEFAULT 0,
                query_signature TEXT,
                feedback_weight REAL DEFAULT 1,
                mapping_signature TEXT,
                mapping_changed INTEGER DEFAULT 0
            )
        ''')

        self._ensure_match_feedback_columns(cursor)

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_match_feedback_signature
            ON match_feedback(query_signature, action)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_match_feedback_normalized
            ON match_feedback(normalized_name, normalized_spec, normalized_unit)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_match_feedback_mapping_signature
            ON match_feedback(mapping_signature)
        ''')

        conn.commit()
        conn.close()

    def save_match_feedback(self, feedback: Dict[str, Any]) -> int:
        """保存匹配确认反馈"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO match_feedback (
                created_at, source_type, template_name, template_hit, action,
                original_name, original_spec, original_unit,
                normalized_name, normalized_spec, normalized_unit,
                selected_product_code, selected_product_name,
                top_candidate_code, top_candidate_name, top_candidate_score,
                top_candidate_rank, selected_rank, selected_score,
                with_product_image, ocr_confidence, query_signature,
                feedback_weight, mapping_signature, mapping_changed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            feedback.get('source_type', ''),
            feedback.get('template_name', ''),
            1 if feedback.get('template_hit') else 0,
            feedback.get('action', ''),
            feedback.get('original_name', ''),
            feedback.get('original_spec', ''),
            feedback.get('original_unit', ''),
            feedback.get('normalized_name', ''),
            feedback.get('normalized_spec', ''),
            feedback.get('normalized_unit', ''),
            feedback.get('selected_product_code', ''),
            feedback.get('selected_product_name', ''),
            feedback.get('top_candidate_code', ''),
            feedback.get('top_candidate_name', ''),
            feedback.get('top_candidate_score', 0),
            feedback.get('top_candidate_rank', 0),
            feedback.get('selected_rank', 0),
            feedback.get('selected_score', 0),
            1 if feedback.get('with_product_image') else 0,
            feedback.get('ocr_confidence', 0),
            feedback.get('query_signature', ''),
            feedback.get('feedback_weight', 1),
            feedback.get('mapping_signature', ''),
            1 if feedback.get('mapping_changed') else 0
        ))
        feedback_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return feedback_id

    def get_match_feedback(
        self,
        normalized_name: str = '',
        normalized_spec: str = '',
        normalized_unit: str = '',
        query_signature: str = '',
        mapping_signature: str = '',
        limit: int = 30
    ) -> List[Dict]:
        """按标准化字段、签名或映射签名查询历史反馈"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if query_signature:
            cursor.execute('''
                SELECT * FROM match_feedback
                WHERE query_signature = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (query_signature, limit))
        elif mapping_signature:
            cursor.execute('''
                SELECT * FROM match_feedback
                WHERE mapping_signature = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (mapping_signature, limit))
        else:
            cursor.execute('''
                SELECT * FROM match_feedback
                WHERE normalized_name = ?
                  AND normalized_spec = ?
                  AND normalized_unit = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (normalized_name, normalized_spec, normalized_unit, limit))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_feedback_summary(
        self,
        normalized_name: str = '',
        normalized_spec: str = '',
        normalized_unit: str = '',
        query_signature: str = '',
        mapping_signature: str = '',
        limit: int = 50
    ) -> Dict[str, Any]:
        """汇总历史反馈用于匹配加权"""
        rows = self.get_match_feedback(
            normalized_name=normalized_name,
            normalized_spec=normalized_spec,
            normalized_unit=normalized_unit,
            query_signature=query_signature,
            mapping_signature=mapping_signature,
            limit=limit
        )

        selected_counts = {}
        selected_image_counts = {}
        no_match_count = 0
        ask_boss_count = 0
        rejected_top_codes = {}
        mapping_changed_count = 0
        template_hit_count = 0

        for row in rows:
            action = row.get('action')
            selected_code = row.get('selected_product_code') or ''
            top_code = row.get('top_candidate_code') or ''
            weight = float(row.get('feedback_weight') or 1)

            if row.get('mapping_changed'):
                mapping_changed_count += 1
            if row.get('template_hit'):
                template_hit_count += 1

            if action == 'select' and selected_code:
                selected_counts[selected_code] = selected_counts.get(selected_code, 0) + weight
                if row.get('with_product_image'):
                    selected_image_counts[selected_code] = selected_image_counts.get(selected_code, 0) + weight
            elif action == 'no_match':
                no_match_count += weight
                if top_code:
                    rejected_top_codes[top_code] = rejected_top_codes.get(top_code, 0) + weight
            elif action == 'ask_boss':
                ask_boss_count += weight
                if top_code:
                    rejected_top_codes[top_code] = rejected_top_codes.get(top_code, 0) + (weight * 0.5)

        return {
            'rows': rows,
            'selected_counts': selected_counts,
            'selected_image_counts': selected_image_counts,
            'rejected_top_codes': rejected_top_codes,
            'no_match_count': no_match_count,
            'ask_boss_count': ask_boss_count,
            'mapping_changed_count': mapping_changed_count,
            'template_hit_count': template_hit_count,
            'feedback_count': len(rows)
        }

    def get_recent_feedback_stats(self, limit: int = 200) -> Dict[str, Any]:
        """获取近期反馈统计"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT action, COUNT(*) as count
            FROM match_feedback
            GROUP BY action
        ''')
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {row['action']: row['count'] for row in rows}

    def close(self):
        """预留关闭接口，兼容后续扩展"""
        return None

    def save_quote(self, quote_data: Dict) -> int:
        """
        保存报价记录

        Args:
            quote_data: 报价数据
                - customer_name: 客户名称
                - quote_file: 原始报价单文件名
                - total_items: 总项数
                - matched_items: 已匹配项数
                - total_amount: 总金额
                - export_file: 导出文件名
                - items: 报价明细列表
                - remark: 备注

        Returns:
            新记录的 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO quote_history
            (created_at, customer_name, quote_file, total_items, matched_items, total_amount, export_file, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            quote_data.get('customer_name', ''),
            quote_data.get('quote_file', ''),
            quote_data.get('total_items', 0),
            quote_data.get('matched_items', 0),
            quote_data.get('total_amount', 0),
            quote_data.get('export_file', ''),
            quote_data.get('remark', '')
        ))

        quote_id = cursor.lastrowid

        items = quote_data.get('items', [])
        for item in items:
            cursor.execute('''
                INSERT INTO quote_items
                (quote_id, item_name, item_quantity, item_unit, item_price,
                 budget_price, product_name, product_code, supplier, match_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                quote_id,
                item.get('item_name', ''),
                item.get('item_quantity', 0),
                item.get('item_unit', ''),
                item.get('item_price', 0),
                item.get('budget_price', 0),
                item.get('product_name', ''),
                item.get('product_code', ''),
                item.get('supplier', ''),
                item.get('match_score', 0)
            ))

        conn.commit()
        conn.close()

        return quote_id

    def get_history_list(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """获取历史记录列表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, created_at, customer_name, quote_file, total_items,
                   matched_items, total_amount, export_file, remark
            FROM quote_history
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_quote_detail(self, quote_id: int) -> Optional[Dict]:
        """获取报价详情（含明细）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, created_at, customer_name, quote_file, total_items,
                   matched_items, total_amount, export_file, remark
            FROM quote_history
            WHERE id = ?
        ''', (quote_id,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        quote = dict(row)

        cursor.execute('''
            SELECT item_name, item_quantity, item_unit, item_price,
                   budget_price, product_name, product_code, supplier, match_score
            FROM quote_items
            WHERE quote_id = ?
        ''', (quote_id,))

        quote['items'] = [dict(item) for item in cursor.fetchall()]
        conn.close()

        return quote

    def delete_quote(self, quote_id: int) -> bool:
        """删除报价记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM quote_items WHERE quote_id = ?', (quote_id,))
        cursor.execute('DELETE FROM quote_history WHERE id = ?', (quote_id,))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def get_statistics(self) -> Dict:
        """获取统计数据"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) as count FROM quote_history')
        total_count = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM quote_history
            WHERE created_at >= date('now', 'start of month')
        ''')
        month_count = cursor.fetchone()['count']

        cursor.execute('SELECT COALESCE(SUM(total_amount), 0) as total FROM quote_history')
        total_amount = cursor.fetchone()['total']

        cursor.execute('''
            SELECT AVG(CAST(matched_items AS FLOAT) / NULLIF(total_items, 0)) as avg_rate
            FROM quote_history
            WHERE total_items > 0
        ''')
        avg_match_rate = cursor.fetchone()['avg_rate'] or 0

        conn.close()

        return {
            'total_count': total_count,
            'month_count': month_count,
            'total_amount': total_amount,
            'avg_match_rate': round(avg_match_rate * 100, 1)
        }
