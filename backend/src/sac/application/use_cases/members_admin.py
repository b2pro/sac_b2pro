from dataclasses import dataclass
from uuid import UUID

from sac.application.ports import (
    PasswordHasherPort,
    TenantRepository,
    UserRepository,
    UserTenantRepository,
)
from sac.application.use_cases.platform_users import (
    CreateUserInput,
    CreateUserUseCase,
    LinkUserToTenantUseCase,
    ResetPasswordUseCase,
    validate_password,
)
from sac.domain.entities import User, UserTenant
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.permissions import Role

# Mensagens compartilhadas entre os use cases desta tela: o admin nunca sabe
# se o alvo existe como super_admin (finge que nao ha usuario nenhum) nem
# consegue mexer no proprio vinculo (perderia o proprio acesso ou criaria um
# tenant sem admin).
_ALVO_NAO_ENCONTRADO = "usuario nao encontrado"
_PROPRIO_VINCULO = "nao e possivel alterar o proprio vinculo"


@dataclass(frozen=True)
class MemberDetail:
    id: UUID
    name: str
    email: str
    role: Role
    active: bool
    user_active: bool


def _member_detail(user: User, link: UserTenant) -> MemberDetail:
    return MemberDetail(
        id=user.id,
        name=user.name,
        email=user.email,
        role=link.role,
        active=link.active,
        user_active=user.active,
    )


@dataclass(frozen=True)
class CreateMemberInput:
    email: str
    role: Role
    name: str | None = None
    password: str | None = None


class CreateMemberUseCase:
    def __init__(
        self,
        users: UserRepository,
        tenants: TenantRepository,
        links: UserTenantRepository,
        hasher: PasswordHasherPort,
    ) -> None:
        self._users = users
        self._tenants = tenants
        self._links = links
        self._hasher = hasher

    async def execute(self, tenant_id: UUID, data: CreateMemberInput) -> MemberDetail:
        # nome e senha sao exigidos e VALIDADOS SEMPRE, antes de qualquer
        # consulta ao banco -- inclusive quando o email ja existe e os dois
        # vao ser descartados (o usuario existente mantem a propria
        # identidade e senha). Se essa checagem so rodasse no ramo "email
        # novo", mandar so {email, role} viraria um oraculo gratuito: 422
        # para email inexistente, 201/404 para email existente, revelando
        # quais emails sao contas de verdade sem gastar uma tentativa sequer.
        # Validar sempre torna a diferenca de status uma consequencia do
        # corpo enviado, nao do estado do banco.
        if not data.name or not data.password:
            raise ValidationError("nome e senha sao obrigatorios")
        validate_password(data.password)

        email = data.email.strip().lower()
        user = await self._users.get_by_email(email)
        if user is None:
            user = await CreateUserUseCase(self._users, self._hasher).execute(
                CreateUserInput(name=data.name, email=email, password=data.password)
            )
        elif user.is_super_admin or await _linked_a_outro_tenant(self._links, user.id, tenant_id):
            # as duas recusas (e super_admin, ou ja pertence a outro tenant)
            # usam a MESMA mensagem/tipo: vincular usuario de outro tenant e
            # privilegio de super_admin (unico papel que hoje cria vinculos
            # pelo painel de plataforma), e o admin deste tenant nao pode
            # distinguir "e da plataforma" de "e de outro tenant" testando
            # emails -- as duas leem como "usuario nao encontrado".
            raise NotFoundError(_ALVO_NAO_ENCONTRADO)

        if await self._links.get(user.id, tenant_id) is not None:
            raise ConflictError("email ja vinculado a este tenant")

        link = await LinkUserToTenantUseCase(self._users, self._tenants, self._links).execute(
            user.id, tenant_id, data.role
        )
        return _member_detail(user, link)


async def _linked_a_outro_tenant(
    links: UserTenantRepository, user_id: UUID, tenant_id: UUID
) -> bool:
    """True se o usuario tiver QUALQUER vinculo (ativo ou nao) com um tenant
    diferente do informado. Vincular ou operar sobre alguem de outro tenant e
    privilegio de super_admin -- o admin de um tenant nao alcanca gente de
    fora dele, nem para criar vinculo novo nem (ver ResetMemberPasswordUseCase)
    para mexer na senha global de quem ja e compartilhado entre tenants.
    """
    return any(link.tenant_id != tenant_id for link in await links.list_for_user(user_id))


async def _resolve_target(
    users: UserRepository,
    links: UserTenantRepository,
    tenant_id: UUID,
    acting_user_id: UUID,
    user_id: UUID,
) -> tuple[User, UserTenant]:
    if user_id == acting_user_id:
        # ninguem altera o proprio papel nem se desativa por aqui: faria o
        # tenant ficar sem admin se o unico admin se rebaixasse ou se desligasse.
        raise ConflictError(_PROPRIO_VINCULO)
    user = await users.get_by_id(user_id)
    if user is None or user.is_super_admin:
        raise NotFoundError(_ALVO_NAO_ENCONTRADO)
    link = await links.get(user_id, tenant_id)
    if link is None:
        # mesma mensagem do ramo acima (usuario ausente ou super_admin): um
        # user_id de outro tenant nao pode devolver um 404 diferente do de um
        # user_id que nao existe em lugar nenhum, senao o admin usa a
        # distincao como oraculo para confirmar que o UUID e uma conta real.
        raise NotFoundError(_ALVO_NAO_ENCONTRADO)
    return user, link


class UpdateMemberLinkUseCase:
    def __init__(self, users: UserRepository, links: UserTenantRepository) -> None:
        self._users = users
        self._links = links

    async def execute(
        self,
        tenant_id: UUID,
        acting_user_id: UUID,
        user_id: UUID,
        role: Role | None,
        active: bool | None,
    ) -> MemberDetail:
        user, link = await _resolve_target(
            self._users, self._links, tenant_id, acting_user_id, user_id
        )
        if role is not None:
            link.role = role
        if active is not None:
            link.active = active
        await self._links.update(link)
        return _member_detail(user, link)


class ResetMemberPasswordUseCase:
    def __init__(
        self, users: UserRepository, links: UserTenantRepository, hasher: PasswordHasherPort
    ) -> None:
        self._users = users
        self._links = links
        self._hasher = hasher

    async def execute(
        self, tenant_id: UUID, acting_user_id: UUID, user_id: UUID, new_password: str
    ) -> None:
        await _resolve_target(self._users, self._links, tenant_id, acting_user_id, user_id)
        # defesa em profundidade: o reset escreve na linha GLOBAL do usuario
        # (password_hash), valida para qualquer tenant onde ele tenha
        # vinculo. CreateMemberUseCase ja impede que o admin deste tenant
        # CRIE um vinculo cruzado (item acima), mas um super_admin pode
        # vincular o mesmo usuario a dois tenants deliberadamente pelo painel
        # de plataforma -- e nesse caso o admin de um dos tenants nao pode
        # trocar a senha que tambem da acesso ao outro. Diferente da recusa
        # de CreateMemberUseCase, esta pode ser explicita: o admin ja sabe
        # que o alvo e membro do proprio tenant (veio da propria listagem),
        # entao nao ha nada novo para esconder aqui.
        if await _linked_a_outro_tenant(self._links, user_id, tenant_id):
            raise ConflictError(
                "nao e possivel alterar a senha de um usuario vinculado a outro tenant"
            )
        # reusa a validacao de tamanho minimo e o hash de platform_users: nao
        # duplicar essa regra aqui.
        await ResetPasswordUseCase(self._users, self._hasher).execute(user_id, new_password)


class ListMembersAdminUseCase:
    """Listagem gerencial (nome, email, papel, estados) para a tela de
    administracao de membros. Distinta de ListTenantMembersUseCase
    (members.py), que alimenta os seletores de atribuicao e por isso fica
    enxuta (sem email) e acessivel a qualquer papel autenticado.
    """

    def __init__(self, users: UserRepository, links: UserTenantRepository) -> None:
        self._users = users
        self._links = links

    async def execute(self, tenant_id: UUID) -> list[MemberDetail]:
        result: list[MemberDetail] = []
        for link in await self._links.list_for_tenant(tenant_id):
            user = await self._users.get_by_id(link.user_id)
            # super_admin nao aparece aqui pelo mesmo motivo do resto do
            # modulo: esse vinculo nao deveria existir, mas se existir nao se
            # revela.
            if user is None or user.is_super_admin:
                continue
            result.append(_member_detail(user, link))
        result.sort(key=lambda m: m.name)
        return result
