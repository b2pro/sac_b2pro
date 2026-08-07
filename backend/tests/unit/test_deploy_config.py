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
ENV_EXEMPLO = RAIZ / ".env.prod.example"
GITIGNORE = RAIZ / ".gitignore"
SCRIPTS_DE_OPERACAO = ("build.sh", "up.sh", "down.sh", "migrate.sh")
DOWN = RAIZ / "down.sh"
STATUS = RAIZ / "status.sh"


def _conteudo_prod() -> str:
    return ENTRYPOINT_PROD.read_text(encoding="utf-8")


def _sem_comentarios(conteudo: str) -> str:
    """Descarta linhas de comentario antes de comparar substring.

    Um comentario pode legitimamente citar o nome de uma flag para explicar
    que o script NAO a usa (e o entrypoint de producao faz isso). Comparar
    substring no arquivo inteiro faz esse comentario quebrar a suite sem
    relacao com o comportamento real do script -- por isso a comparacao roda
    so sobre as linhas executaveis.
    """
    linhas = [linha for linha in conteudo.splitlines() if not linha.strip().startswith("#")]
    return "\n".join(linhas)


def test_entrypoint_de_prod_existe() -> None:
    assert ENTRYPOINT_PROD.is_file()


def test_entrypoint_de_prod_nao_usa_reload() -> None:
    """--reload derruba os workers (uvicorn recusa reload com --workers) e
    reinicia o processo a cada arquivo tocado."""
    assert "--reload" not in _sem_comentarios(_conteudo_prod())


def test_entrypoint_de_prod_nao_roda_seed() -> None:
    """O super admin nasce por comando manual: deixar o seed no boot exige a
    senha do admin permanente no ambiente do servidor."""
    assert "sac.infrastructure.seed" not in _sem_comentarios(_conteudo_prod())


def test_entrypoint_de_prod_roda_as_migrations() -> None:
    """Sem isto o container sobe e responde 500 em toda rota com tabela
    faltando depois de um deploy que trouxe migration nova. Filtrar
    comentarios so torna esta assercao mais forte: um comentario que apenas
    cite o comando de migration deixa de bastar para o teste passar."""
    assert "sac.infrastructure.migrate all" in _sem_comentarios(_conteudo_prod())


def _conteudo_compose() -> str:
    return _sem_comentarios(COMPOSE_PROD.read_text(encoding="utf-8"))


def test_compose_de_prod_existe() -> None:
    assert COMPOSE_PROD.is_file()


def test_compose_de_prod_nao_declara_ambiente_de_desenvolvimento() -> None:
    """SAC_ENVIRONMENT=development faz ensure_boot_secrets liberar o boot com o
    segredo publico do repositorio, e a aplicacao passa a assinar token
    forjavel -- quem tem o segredo emite um access token com `sa: true` e vira
    super_admin.

    O compose de prod nao define SAC_ENVIRONMENT (vem do .env.prod), entao este
    teste cobre apenas o caso de alguem inline-ar o valor errado aqui. O que
    esta no .env.prod da VPS nenhum teste alcanca -- por isso o teste seguinte
    trava o modelo, que e o arquivo de onde a copia sai.
    """
    conteudo = _conteudo_compose()
    assert "SAC_ENVIRONMENT: development" not in conteudo
    assert "SAC_ENVIRONMENT=development" not in conteudo


def test_env_de_exemplo_declara_producao() -> None:
    conteudo = _sem_comentarios(ENV_EXEMPLO.read_text(encoding="utf-8"))
    assert "SAC_ENVIRONMENT=production" in conteudo
    assert "SAC_ENVIRONMENT=development" not in conteudo


def test_env_de_exemplo_nao_traz_segredo_preenchido() -> None:
    """O modelo existe para ser copiado: valor real aqui vaza no git. Comparacao
    por linha, e nao por substring com \\n, porque o arquivo pode ter CRLF."""
    valores = {}
    for linha in ENV_EXEMPLO.read_text(encoding="utf-8").splitlines():
        limpa = linha.strip()
        if limpa and not limpa.startswith("#") and "=" in limpa:
            chave, _, valor = limpa.partition("=")
            valores[chave.strip()] = valor.strip()
    for chave in ("SAC_JWT_SECRET", "POSTGRES_PASSWORD", "SAC_S3_SECRET_KEY"):
        assert chave in valores, f"{chave} deveria estar no modelo"
        assert valores[chave] == "", f"{chave} deveria estar vazio no modelo"


def test_gitignore_cobre_o_env_de_producao() -> None:
    """A regra `.env` do .gitignore casa apenas com o nome exato: sem uma linha
    propria, `.env.prod` -- que tem o segredo JWT e a senha do banco -- entra
    num `git add .` sem aviso nenhum."""
    linhas = GITIGNORE.read_text(encoding="utf-8").splitlines()
    assert ".env.prod" in [linha.strip() for linha in linhas]


def test_compose_de_prod_nao_publica_porta_do_banco() -> None:
    """O Postgres nao pode ficar exposto na interface publica da VPS. Em prod o
    unico acesso e pela rede interna do compose."""
    assert "5432:5432" not in _conteudo_compose()


def test_compose_de_prod_usa_o_entrypoint_de_prod() -> None:
    conteudo = _conteudo_compose()
    assert "docker-entrypoint.prod.sh" in conteudo
    assert "docker-entrypoint.sh" not in conteudo.replace("docker-entrypoint.prod.sh", "")


def test_compose_de_prod_nao_monta_o_codigo_do_host() -> None:
    """Volume de codigo e recurso de desenvolvimento: em producao o container
    tem de rodar o que esta na imagem construida, nao o que esta no disco da
    VPS."""
    assert "./backend:/app" not in _conteudo_compose()


def test_compose_de_prod_publica_a_porta_do_web_so_no_loopback() -> None:
    """A porta publicada do `web` precisa comecar com `127.0.0.1:`: sem o host
    fixo, um valor como `SAC_WEB_PORT=8080` (leitura natural do nome da
    variavel) publica em 0.0.0.0 e expoe a aplicacao inteira em HTTP puro no
    IP da VPS -- e a publicacao de porta do Docker entra por
    DOCKER-USER/PREROUTING, entao um firewall do host nao bloqueia."""
    linhas_de_porta = [
        linha.strip()
        for linha in _conteudo_compose().splitlines()
        if linha.strip().endswith(':80"')
    ]
    assert linhas_de_porta, "linha de porta publicada do web nao encontrada"
    for linha in linhas_de_porta:
        assert linha.startswith('- "127.0.0.1:'), linha


def test_scripts_de_operacao_apontam_para_o_compose_de_producao() -> None:
    """Os scripts do dia a dia rodam na VPS, onde o clone traz TAMBEM o compose de
    desenvolvimento. Um deles que esqueca o `-f docker-compose.prod.yml` sobe o
    compose de dev: Postgres em 5432 com senha `sac`, backend em 8000, tudo em
    0.0.0.0, e SAC_ENVIRONMENT=development liberando o boot com o segredo publico
    do repositorio. E o mesmo desastre que docs/deploy.md manda evitar, so que
    disparado por um script que parece seguro.
    """
    for nome in SCRIPTS_DE_OPERACAO:
        caminho = RAIZ / nome
        assert caminho.is_file(), f"{nome} nao existe"
        executavel = _sem_comentarios(caminho.read_text(encoding="utf-8"))
        assert "-f docker-compose.prod.yml" in executavel, nome
        assert "--env-file .env.prod" in executavel, nome


def test_status_e_somente_leitura() -> None:
    """`status.sh` e o unico script da raiz que pode olhar o compose de
    desenvolvimento (com `--dev`), e por isso fica de fora da guarda acima. O que
    torna isso seguro nao e a intencao de quem escreveu, e nao poder mexer em
    nada: ele so consulta. Se um dia alguem lhe der um `up`, um `restart` ou um
    `build`, o script passa a ser capaz de subir a stack de dev na VPS -- que e
    exatamente o desastre que a guarda acima existe para impedir.
    """
    executavel = _sem_comentarios(STATUS.read_text(encoding="utf-8"))
    assert "-f docker-compose.prod.yml" in executavel, "status.sh nao olha a stack de producao"
    for verbo in (" up ", " down ", " start ", " stop ", " restart ", " build ", " rm "):
        assert verbo not in f" {executavel} ".replace("\n", " "), (
            f"status.sh ganhou um comando que muda estado: {verbo.strip()}"
        )


def test_down_exige_confirmacao_antes_de_apagar_volume() -> None:
    """`down --volumes` no compose de producao apaga o volume do Postgres: perde o
    banco inteiro, sem backup automatico por tras (ver docs/deploy.md). Passar a
    flag sem confirmacao e um caractere de distancia de `down` normal, entao o
    script tem de pedir confirmacao explicita em vez de obedecer direto.
    """
    executavel = _sem_comentarios(DOWN.read_text(encoding="utf-8"))
    assert "--volumes" in executavel, "down.sh nao reconhece a flag de volume"
    assert "read" in executavel, "down.sh nao pede confirmacao"


def test_down_recusa_apagar_volume_sem_terminal() -> None:
    """Sem TTY nao ha como confirmar. Obedecer nesse caso transformaria um
    `down.sh --volumes` dentro de qualquer automacao na perda do banco.
    """
    executavel = _sem_comentarios(DOWN.read_text(encoding="utf-8"))
    assert "-t 0" in executavel, "down.sh nao verifica se ha terminal"
