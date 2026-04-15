from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data'


def profile_products() -> dict[str, Any]:
    path = DATA_DIR / 'products.json'
    if not path.exists():
        return {'exists': False}

    items = json.loads(path.read_text(encoding='utf-8'))
    brands = {item.get('brand') for item in items if item.get('brand')}
    suppliers = {item.get('supplier') for item in items if item.get('supplier')}
    categories = {item.get('category') for item in items if item.get('category')}

    return {
        'exists': True,
        'path': str(path),
        'count': len(items),
        'fields': list(items[0].keys()) if items else [],
        'unique_brands': len(brands),
        'unique_suppliers': len(suppliers),
        'unique_categories': len(categories),
        'status_distribution': dict(Counter(item.get('status') for item in items)),
        'empty_model_count': sum(1 for item in items if not item.get('model')),
        'with_intro_count': sum(1 for item in items if item.get('intro')),
    }


def profile_sqlite(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    if not path.exists():
        return {'exists': False, 'path': str(path)}

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    table_details: dict[str, Any] = {}
    for table in tables:
        columns = [row[1] for row in cur.execute(f'PRAGMA table_info({table})')]
        count = cur.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        table_details[table] = {'columns': columns, 'count': count}
    conn.close()

    return {
        'exists': True,
        'path': str(path),
        'tables': table_details,
    }


def profile_json(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    if not path.exists():
        return {'exists': False, 'path': str(path)}

    data = json.loads(path.read_text(encoding='utf-8'))
    payload: dict[str, Any] = {
        'exists': True,
        'path': str(path),
        'type': type(data).__name__,
    }

    if isinstance(data, dict):
        payload['keys'] = list(data.keys())
    elif isinstance(data, list):
        payload['count'] = len(data)
        payload['sample_keys'] = list(data[0].keys()) if data and isinstance(data[0], dict) else []

    return payload


def main() -> None:
    report = {
        'products_json': profile_products(),
        'quote_history_db': profile_sqlite('quote_history.db'),
        'ai_cache_db': profile_sqlite('ai_cache.db'),
        'synonyms_json': profile_json('synonyms.json'),
        'parse_templates_json': profile_json('parse_templates.json'),
        'normalization_rules_json': profile_json('normalization_rules.json'),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
