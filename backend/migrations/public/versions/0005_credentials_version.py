"""Versao de credencial em users: permite revogar sessao na troca de senha

Revision ID: 0005_credentials_version
Revises: 0004_user_preferences
Create Date: 2026-08-05

A autenticacao e JWT stateless (sem jti, sem denylist), entao antes desta coluna
nao havia como invalidar um token ja emitido: um refresh token roubado sobrevivia
a troca de senha por todo o TTL de 7 dias, e resetar a senha -- a resposta padrao
a um incidente -- nao continha nada.

A coluna e o contador que o token carrega no claim `cv` e que o refresh reconfere
contra o banco. `server_default 1` porque os tokens do formato anterior nao tem o
claim: eles decodificam como zero e nunca batem com 1, o que forca um relogin de
todos no deploy. Isso e desejado -- e o unico jeito de garantir que nenhuma sessao
anterior ao versionamento continue renovando.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_credentials_version"
down_revision = "0004_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("credentials_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("users", "credentials_version")
