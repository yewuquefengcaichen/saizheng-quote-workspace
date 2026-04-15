from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import NormalizationRule, ParseTemplate, Synonym  # noqa: E402

DATA_DIR = BACKEND_ROOT.parent / 'data'


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = ' '.join(str(value).split())
    return value or None


@dataclass
class RuleImportStats:
    synonym_pairs_created: int = 0
    synonym_pairs_updated: int = 0
    normalization_rules_created: int = 0
    normalization_rules_updated: int = 0
    parse_templates_created: int = 0
    parse_templates_updated: int = 0


class LegacyRuleImporter:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.stats = RuleImportStats()

    async def run(self) -> None:
        synonyms = json.loads((DATA_DIR / 'synonyms.json').read_text(encoding='utf-8'))
        normalization_rules = json.loads((DATA_DIR / 'normalization_rules.json').read_text(encoding='utf-8'))
        parse_templates = json.loads((DATA_DIR / 'parse_templates.json').read_text(encoding='utf-8'))

        async with AsyncSessionLocal() as session:
            await self.import_synonyms(session, synonyms)
            await self.import_normalization_rules(session, normalization_rules)
            await self.import_parse_templates(session, parse_templates)

            if self.dry_run:
                await session.rollback()
                print('[legacy-rules] dry-run complete, transaction rolled back')
            else:
                await session.commit()
                print('[legacy-rules] import committed')

        print(self.stats)

    async def import_synonyms(self, session, synonyms: dict[str, list[str]]) -> None:
        for canonical_term, synonym_list in synonyms.items():
            canonical = normalize_text(canonical_term)
            if not canonical:
                continue
            for synonym_term in synonym_list:
                synonym = normalize_text(synonym_term)
                if not synonym:
                    continue
                row = await session.scalar(
                    select(Synonym).where(
                        Synonym.canonical_term == canonical,
                        Synonym.synonym_term == synonym,
                    )
                )
                if row is None:
                    row = Synonym(canonical_term=canonical, synonym_term=synonym)
                    session.add(row)
                    self.stats.synonym_pairs_created += 1
                else:
                    self.stats.synonym_pairs_updated += 1
                row.is_bidirectional = True
                row.weight = 1
                row.source_type = 'legacy_json'
                row.notes = 'Imported from data/synonyms.json'

    async def import_normalization_rules(self, session, rules: dict[str, Any]) -> None:
        for canonical_term, aliases in rules.get('name_aliases', {}).items():
            await self.upsert_rule(
                session,
                rule_type='name_aliases',
                rule_key=normalize_text(canonical_term),
                rule_value_json=list(aliases),
                source_payload={'legacy_source': 'normalization_rules.json:name_aliases'},
            )

        for canonical_unit, aliases in rules.get('unit_mappings', {}).items():
            await self.upsert_rule(
                session,
                rule_type='unit_mappings',
                rule_key=normalize_text(canonical_unit),
                rule_value_json=list(aliases),
                source_payload={'legacy_source': 'normalization_rules.json:unit_mappings'},
            )

        for index, pair in enumerate(rules.get('spec_patterns', [])):
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            pattern, replacement = pair
            await self.upsert_rule(
                session,
                rule_type='spec_patterns',
                rule_key=str(pattern),
                rule_value_text=str(replacement),
                sort_order=index,
                source_payload={'legacy_source': 'normalization_rules.json:spec_patterns'},
            )

    async def upsert_rule(
        self,
        session,
        *,
        rule_type: str,
        rule_key: str | None,
        rule_value_text: str | None = None,
        rule_value_json: Any = None,
        sort_order: int = 0,
        source_payload: dict[str, Any] | None = None,
    ) -> None:
        row = await session.scalar(
            select(NormalizationRule).where(
                NormalizationRule.rule_type == rule_type,
                NormalizationRule.rule_key == rule_key,
                NormalizationRule.sort_order == sort_order,
            )
        )
        if row is None:
            row = NormalizationRule(rule_type=rule_type, rule_key=rule_key, sort_order=sort_order)
            session.add(row)
            self.stats.normalization_rules_created += 1
        else:
            self.stats.normalization_rules_updated += 1

        row.rule_value_text = rule_value_text
        row.rule_value_json = rule_value_json
        row.is_active = True
        row.source_type = 'legacy_json'
        row.source_payload = source_payload

    async def import_parse_templates(self, session, payload: dict[str, Any]) -> None:
        for template in payload.get('templates', []):
            name = normalize_text(template.get('name'))
            if not name:
                continue
            row = await session.scalar(select(ParseTemplate).where(ParseTemplate.name == name))
            if row is None:
                row = ParseTemplate(name=name)
                session.add(row)
                self.stats.parse_templates_created += 1
            else:
                self.stats.parse_templates_updated += 1

            row.source_type = normalize_text(template.get('source_type')) or 'excel'
            row.header_rows = template.get('header_rows')
            row.column_mapping = template.get('column_mapping')
            row.last_confirmed_mapping = template.get('last_confirmed_mapping')
            row.identifiers = template.get('identifiers')
            row.header_signature = template.get('header_signature')
            row.identifier_signature = template.get('identifier_signature')
            row.usage_count = int(template.get('usage_count') or 0)
            row.confirm_count = int(template.get('confirm_count') or 0)
            row.manual_save_count = int(template.get('manual_save_count') or 0)
            row.template_hit_count = int(template.get('template_hit_count') or 0)
            row.mapping_change_count = int(template.get('mapping_change_count') or 0)
            row.mapping_signature = template.get('mapping_signature')
            row.last_mapping_changed = bool(template.get('last_mapping_changed') or False)
            row.source_payload = template


def parse_args() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description='Import legacy rules JSON into PostgreSQL V2 schema')
    parser.add_argument('--dry-run', action='store_true', help='Run import but rollback at the end')
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    importer = LegacyRuleImporter(dry_run=args.dry_run)
    await importer.run()


if __name__ == '__main__':
    asyncio.run(async_main())
