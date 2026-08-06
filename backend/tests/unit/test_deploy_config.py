"""Guardas de configuracao de deploy.

Estes testes nao exercitam codigo da aplicacao: eles leem os arquivos de deploy
e travam as caracteristicas cuja perda seria silenciosa em producao. O modo de
falha que eles cobrem e concreto -- alguem copia o entrypoint ou o compose de
desenvolvimento por cima do de producao, tudo sobe normalmente, e a aplicacao
passa a assinar token com o segredo publico do repositorio ou a rodar com
`--reload` e um unico worker.
"""

from pathlib import Path

# tests/unit/test_deploy_config.py -> tests/unit -> tests -> backend -> raiz
RAIZ = Path(__file__).resolve().parents[3]
ENTRYPOINT_PROD = RAIZ / "backend" / "docker-entrypoint.prod.sh"
COMPOSE_PROD = RAIZ / "docker-compose.prod.yml"


def test_entrypoint_de_prod_existe() -> None:
    assert ENTRYPOINT_PROD.is_file()


def test_entrypoint_de_prod_nao_usa_reload() -> None:
    """--reload derruba os workers (uvicorn recusa reload com --workers) e
    reinicia o processo a cada arquivo tocado."""
    assert "--reload" not in ENTRYPOINT_PROD.read_text(encoding="utf-8")


def test_entrypoint_de_prod_nao_roda_seed() -> None:
    """O super admin nasce por comando manual: deixar o seed no boot exige a
    senha do admin permanente no ambiente do servidor."""
    assert "sac.infrastructure.seed" not in ENTRYPOINT_PROD.read_text(encoding="utf-8")


def test_entrypoint_de_prod_roda_as_migrations() -> None:
    """Sem isto o container sobe e responde 500 em toda rota com tabela
    faltando depois de um deploy que trouxe migration nova."""
    conteudo = ENTRYPOINT_PROD.read_text(encoding="utf-8")
    assert "sac.infrastructure.migrate all" in conteudo
