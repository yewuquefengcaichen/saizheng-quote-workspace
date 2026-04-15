"""init rules and feedback tables

Revision ID: 20260415_0003
Revises: 20260415_0002
Create Date: 2026-04-15 23:05:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260415_0003'
down_revision = '20260415_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'synonyms',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('canonical_term', sa.String(length=120), nullable=False),
        sa.Column('synonym_term', sa.String(length=120), nullable=False),
        sa.Column('source_type', sa.String(length=50), server_default='legacy_json', nullable=False),
        sa.Column('is_bidirectional', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('weight', sa.Integer(), server_default='1', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('canonical_term', 'synonym_term', name='uq_synonyms_pair'),
    )
    op.create_index(op.f('ix_synonyms_canonical_term'), 'synonyms', ['canonical_term'], unique=False)
    op.create_index(op.f('ix_synonyms_synonym_term'), 'synonyms', ['synonym_term'], unique=False)

    op.create_table(
        'normalization_rules',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('rule_type', sa.String(length=50), nullable=False),
        sa.Column('rule_key', sa.String(length=255), nullable=True),
        sa.Column('rule_value_text', sa.Text(), nullable=True),
        sa.Column('rule_value_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('source_type', sa.String(length=50), server_default='legacy_json', nullable=False),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_normalization_rules_rule_key'), 'normalization_rules', ['rule_key'], unique=False)
    op.create_index(op.f('ix_normalization_rules_rule_type'), 'normalization_rules', ['rule_type'], unique=False)

    op.create_table(
        'parse_templates',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=50), server_default='excel', nullable=False),
        sa.Column('header_rows', sa.Integer(), nullable=True),
        sa.Column('column_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_confirmed_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('identifiers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('header_signature', sa.Text(), nullable=True),
        sa.Column('identifier_signature', sa.Text(), nullable=True),
        sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('confirm_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('manual_save_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('template_hit_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('mapping_change_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('mapping_signature', sa.Text(), nullable=True),
        sa.Column('last_mapping_changed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_parse_templates_name'), 'parse_templates', ['name'], unique=True)

    op.create_table(
        'match_feedback',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_type', sa.String(length=50), nullable=True),
        sa.Column('template_name', sa.String(length=255), nullable=True),
        sa.Column('template_hit', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=True),
        sa.Column('original_name', sa.Text(), nullable=True),
        sa.Column('original_spec', sa.Text(), nullable=True),
        sa.Column('original_unit', sa.String(length=64), nullable=True),
        sa.Column('normalized_name', sa.Text(), nullable=True),
        sa.Column('normalized_spec', sa.Text(), nullable=True),
        sa.Column('normalized_unit', sa.String(length=64), nullable=True),
        sa.Column('selected_product_code', sa.String(length=120), nullable=True),
        sa.Column('selected_product_name', sa.Text(), nullable=True),
        sa.Column('top_candidate_code', sa.String(length=120), nullable=True),
        sa.Column('top_candidate_name', sa.Text(), nullable=True),
        sa.Column('top_candidate_score', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('top_candidate_rank', sa.Integer(), nullable=True),
        sa.Column('selected_rank', sa.Integer(), nullable=True),
        sa.Column('selected_score', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('with_product_image', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('ocr_confidence', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('query_signature', sa.Text(), nullable=True),
        sa.Column('feedback_weight', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('mapping_signature', sa.Text(), nullable=True),
        sa.Column('mapping_changed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_match_feedback_selected_product_code'), 'match_feedback', ['selected_product_code'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_match_feedback_selected_product_code'), table_name='match_feedback')
    op.drop_table('match_feedback')

    op.drop_index(op.f('ix_parse_templates_name'), table_name='parse_templates')
    op.drop_table('parse_templates')

    op.drop_index(op.f('ix_normalization_rules_rule_type'), table_name='normalization_rules')
    op.drop_index(op.f('ix_normalization_rules_rule_key'), table_name='normalization_rules')
    op.drop_table('normalization_rules')

    op.drop_index(op.f('ix_synonyms_synonym_term'), table_name='synonyms')
    op.drop_index(op.f('ix_synonyms_canonical_term'), table_name='synonyms')
    op.drop_table('synonyms')
