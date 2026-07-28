# Design — SAC-B2PRO Fase 2B (Anexos, previews e membros do tenant)

Data: 2026-07-28. Status: aprovado pelo usuario em 2026-07-28. Fontes: `docs/PRD.md` (secao 7), `docs/armazenamento-anexos.md`, `docs/legado-funcionamento.md`, design da Fase 2A.

## Objetivo

Fechar o que a Fase 2A deixou reservado: anexos de ticket no Wasabi S3 com upload direto por presigned URL, previews gerados por worker, e a foto de catalogo do produto (pendencia da Fase 1). Entra tambem o endpoint de membros do tenant, que destrava o seletor de supervisor no ticket.

Fora de escopo: galeria de midias (Fase 3, consome os previews desta fase), dashboard e relatorios (Fase 3), notificacoes (Fase 4).

## Decisoes fechadas com o usuario (2026-07-28)

1. **Storage em dev e teste: MinIO no compose.** Mesmo SDK (boto3), endpoint diferente; Wasabi so em producao via variaveis de ambiente. Os testes de integracao exercitam presigned URL e HEAD de verdade, sem custo nem rede externa.
2. **Worker: fila em tabela + processo separado.** Nenhuma dependencia nova de infra (sem Redis); `python -m sac.worker` como servico do compose, retry com backoff e idempotencia.
3. **Membros do tenant: legivel por qualquer papel de tenant, payload minimo** (`id`, `nome`, `papel`, `ativo`). O atendente precisa escolher supervisor ao abrir ticket. Sem e-mail nem dados administrativos. O CRUD de usuarios por tenant continua fora de escopo (hoje so o super admin, no painel da plataforma).
4. **Tipos aceitos: imagem (jpg/png/webp), PDF e video (mp4/mov/webm), ate 50 MB por arquivo**, no maximo 10 por ticket. Imagens sao comprimidas no client acima de ~2 MB ou 2000px. **Video nao sofre processamento nenhum no servidor**: se nao couber em 50 MB, e recusado no ato.
5. **Thumb de video sai do navegador**, antes do upload: `<video>` + canvas, enviada como objeto de preview. Nada de ffmpeg na imagem do worker. Se o navegador nao decodificar o codec, o anexo fica com placeholder.
6. **Exclusao de anexo e soft delete com objeto preservado** no bucket (evidencia de garantia nao se apaga). Permitido a quem anexou e a admin/supervisor; bloqueado em ticket encerrado.
7. **Foto de catalogo do produto entra nesta fase**, reusando presigned PUT e worker, em prefixo proprio.

## Abordagem: compartilhar a infra, nao a tabela

Um `StoragePort` unico (presigned PUT/GET, HEAD, delete) e uma fila `preview_jobs` global servem os dois casos de uso, mas `ticket_attachments` e uma tabela propria com `ticket_id NOT NULL`, e a foto do produto grava direto em `products.photo_key` / `photo_preview_key`.

Motivo: produto tem **uma** foto, sem ciclo de vida proprio; ticket tem **N** anexos com estados pendente/disponivel e previews. Alternativas descartadas: tabela `media` polimorfica (ganha DRY, perde integridade referencial e complica toda query) e duas implementacoes separadas de ponta a ponta (duplicaria gateway e worker).

## 1. Dados

### `ticket_attachments` (schema do tenant, migration tenant `0004`)

`id`, `ticket_id FK NOT NULL`, `filename`, `content_type`, `size_bytes`, `object_key` (gerada no servidor), `kind` (`imagem`/`pdf`/`video`), `status` (`pendente`/`disponivel`/`expirado`), `preview_key NULL`, `preview_medium_key NULL`, `preview_status` (`sem_preview`/`pendente`/`pronto`/`falhou`), `author_user_id`, `created_at`, `confirmed_at NULL`, `deleted_at NULL`. Indices: `(ticket_id)`, `(status)`, `(preview_status)`. Constraints nomeadas no padrao da Fase 2A (`fk_ticket_attachments_ticket_id`, `ck_ticket_attachments_size`).

Chave do objeto: `{tenant_slug}/{ticket_id}/{uuid}.{ext}`; previews em `{tenant_slug}/{ticket_id}/previews/{uuid}.webp` e `..._medium.webp`.

### `products` (migration tenant `0004`, mesma revisao)

Ganha `photo_preview_key` (nullable). `photo_key` ja existe desde a Fase 1.

### `public.preview_jobs` (migration public)

Global de proposito, para um worker unico varrer todos os tenants sem iterar schemas: `id`, `tenant_slug`, `attachment_id NULL`, `product_id NULL`, `object_key`, `kind`, `status` (`pendente`/`processando`/`pronto`/`falhou`), `attempts`, `next_attempt_at`, `last_error NULL`, `created_at`, `updated_at`. Exatamente um de `attachment_id`/`product_id` preenchido (check constraint). Indice em `(status, next_attempt_at)`.

## 2. Dominio e application

- `domain/attachments.py`: `AttachmentKind`, `AttachmentStatus`, `PreviewStatus`, entidade `TicketAttachment`, entidade `PreviewJob`; funcoes puras `kind_for(content_type) -> AttachmentKind` (mime fora da lista -> `ValidationError`), `validate_size(kind, size_bytes)` (50 MB por arquivo), `build_object_key(tenant_slug, ticket_id, filename) -> str` (extensao derivada do mime, nome do arquivo nunca usado na chave), `next_backoff(attempts) -> timedelta` (exponencial: 1, 2, 4, 8, 16 min; maximo 5 tentativas).
- `application/ports_attachments.py`: `StoragePort` (`presigned_put(key, content_type, max_bytes, ttl) -> str`, `presigned_get(key, ttl) -> str`, `head(key) -> ObjectHead | None`, `put_bytes(key, data, content_type)`, `get_bytes(key) -> bytes`), `AttachmentRepository`, `PreviewJobRepository`, `ProductPhotoRepository`.
- Use cases (`use_cases/attachments.py`): `RequestUploadUseCase` (valida permissao no ticket, mime, tamanho e cota de 10; grava `pendente`; devolve `anexo_id` + URL), `ConfirmUploadUseCase` (HEAD no objeto, compara tamanho e mime reais, marca `disponivel`, enfileira preview quando `imagem`, aceita a thumb ja enviada quando `video`), `ListAttachmentsUseCase` (devolve com presigned GET dos previews prontos), `GetAttachmentUrlUseCase` (presigned GET do original), `DeleteAttachmentUseCase` (soft delete com regra de dono/papel), `ExpirePendingUseCase` (pendentes com mais de 30 min viram `expirado`).
- Use cases da foto do produto (`use_cases/product_photo.py`): `RequestProductPhotoUploadUseCase`, `ConfirmProductPhotoUseCase`, `DeleteProductPhotoUseCase` — mesmas validacoes, prefixo `{tenant_slug}/catalogo/produtos/{product_id}/{uuid}.{ext}`.
- `use_cases/members.py`: `ListTenantMembersUseCase` — junta `user_tenants` com `users` no schema publico, filtra pelo tenant do token, ordena por nome.

Permissoes: anexar, confirmar e excluir exigem `COMENTAR_ANEXAR`; excluir anexo de outro autor exige `DECIDIR_TICKET` (admin/supervisor). Ler anexos segue a regra de visao do ticket (`get_ticket_or_404`). Foto de produto: `GERENCIAR_CADASTROS` para gravar e excluir. Membros: qualquer papel de tenant.

## 3. API

Anexos, no router de tickets:

- `POST /api/tickets/{id}/anexos/intencao` — body `{filename, content_type, size_bytes, with_preview}`; resposta `{anexo_id, upload_url, preview_upload_url (so quando with_preview), object_key, expires_in}`. `with_preview` e usado pelo video: o client ja capturou a thumb no navegador e sobe as duas coisas sem uma segunda ida ao servidor.
- `POST /api/tickets/{id}/anexos/{anexo_id}/confirmar` — sem body; o backend faz HEAD no original (obrigatorio) e no preview quando a intencao previu um, definindo `preview_status` como `pronto` ou `sem_preview`. Resposta e o anexo.
- `GET /api/tickets/{id}/anexos` — lista dos `disponivel` nao deletados, com `preview_url` quando `pronto`.
- `GET /api/tickets/{id}/anexos/{anexo_id}/url?variante=medio|original` — `{url, expires_in}`. Imagem abre por padrao na variante `medio` (rapida); `original` serve o download e os casos sem preview (PDF, video).
- `DELETE /api/tickets/{id}/anexos/{anexo_id}` — 204.

Produto: `POST /api/cadastros/produtos/{id}/foto/intencao`, `POST .../foto/confirmar`, `DELETE .../foto`. `GET /api/cadastros/produtos` passa a devolver `photo_url` (presigned da thumb) quando existir.

Membros: `GET /api/membros`.

Erros no handler unico: 403 sem permissao; 404 ticket/anexo inexistente ou fora da visao; 409 ticket encerrado ou cota de 10 excedida; 422 mime nao aceito, tamanho acima de 50 MB, ou confirmacao cujo HEAD divergiu do declarado; 503 `storage_indisponivel` quando o S3 nao responde (novo `StorageUnavailableError`, mapeado como o `cep_indisponivel` da Fase 1).

## 4. Worker de previews

`python -m sac.worker` (novo servico `worker` no compose, mesma imagem do backend). Loop: `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` sobre `preview_jobs` com `status='pendente' AND next_attempt_at <= now()`; marca `processando`; baixa o original; gera thumb WebP ~400px e media ~1200px com Pillow (`Image.thumbnail`, respeitando proporcao, `MAX_IMAGE_PIXELS` limitado para nao estourar memoria); grava os dois objetos; atualiza o anexo (ou o produto) para `pronto`; commita. Excecao: `attempts += 1`, `next_attempt_at = now() + next_backoff(attempts)`, `last_error` gravado; na quinta tentativa marca `falhou` e o anexo fica `falhou` (UI mostra placeholder). Concorrencia 1, intervalo de 2 s quando a fila esta vazia, `--once` para rodar um ciclo em teste.

`ExpirePendingUseCase` roda no mesmo processo, a cada 5 minutos.

Dependencias novas: `boto3` e `Pillow` no backend.

## 5. Configuracao

Novas variaveis (prefixo `SAC_`): `s3_endpoint_url`, `s3_region`, `s3_bucket`, `s3_access_key`, `s3_secret_key`, `s3_public_endpoint_url` (opcional), `attachment_max_bytes` (default 52428800), `attachment_max_per_ticket` (10), `presigned_ttl_seconds` (300), `pending_expiration_minutes` (30).

**Dois clients boto3, nao um com troca de host.** A assinatura do presigned cobre o header `Host`, entao reescrever o endereco depois de assinar invalida a URL. O gateway mantem dois clients: um interno (`s3_endpoint_url`, ex. `http://minio:9000`) para HEAD, download e upload de previews feitos pelo servidor, e um publico (`s3_public_endpoint_url`, ex. `http://localhost:9000`) usado **apenas** para gerar as URLs assinadas que vao ao navegador. Em producao as duas variaveis apontam para o mesmo endpoint do Wasabi.

Compose ganha `minio` (com console em 9001) e um `minio-init` que cria o bucket `sac-dev` na subida; o `worker` compartilha o ambiente do backend. `dev.ps1` passa a subir os quatro servicos.

## 6. Frontend

- `lib/media.ts` — isolado de proposito, para o componente de upload nao virar um arquivao: `compressImage(file)` (canvas, acima de 2 MB ou 2000px), `captureVideoThumb(file)` (`<video>` + `seek` ~1s + canvas, com timeout e retorno nulo em falha), `kindOf(file)`.
- `lib/attachments.ts` — client da API (intencao, PUT direto no S3 com `XMLHttpRequest` para ter progresso, confirmar, listar, url, excluir).
- `components/tickets/AttachmentsCard.tsx` — substitui o placeholder: dropzone com drag-and-drop, grid de miniaturas com barra de progresso por arquivo, badge de estado (`enviando`/`processando`/`falhou`), clique abre a variante `medio` em nova aba (ou o original quando nao ha preview), PDF com icone, video com a thumb capturada, acao de baixar o original e menu de excluir com dialog de confirmacao. Sem acoes para visualizador e em ticket encerrado.
- Produtos: campo de foto na pagina de cadastro reusando `lib/media.ts`, com thumb na tabela.
- Seletor de supervisor (`Select` alimentado por `GET /api/membros`) na criacao e no dialog de editar ticket — fecha a pendencia registrada na Fase 2A.
- Identidade visual de sempre: `docs/identidade-visual.md`, skill `frontend-design`, sem emojis.

## 7. Testes

- Unit: `kind_for` e `validate_size` (mime aceito/recusado, limite de 50 MB), `build_object_key` (extensao pelo mime, nome do arquivo ignorado), `next_backoff`, cota de 10 e regras de permissao dos use cases com fakes (incluindo `StoragePort` fake).
- Integracao contra MinIO real (fixture que cria bucket descartavel por sessao): intencao gera chave no formato esperado; PUT com content-type diferente do assinado e recusado pelo bucket; confirmacao sem objeto -> 422; HEAD com tamanho divergente -> 422; cota barra o 11º; pendente expira; soft delete some da listagem e o objeto continua no bucket; worker gera os dois previews e marca `pronto`; job que falha 5 vezes vira `falhou`; isolamento entre tenants nas chaves.
- E2E Playwright: upload de um PNG pequeno de fixture pelo dropzone ate a miniatura aparecer, e recusa de um arquivo de tipo invalido.

## 8. Mudancas em codigo existente

- `domain/errors.py`: `StorageUnavailableError` (code `storage_indisponivel`, HTTP 503).
- `interface/errors.py`: novo code no `STATUS_BY_CODE`.
- `interface/routers/tickets.py`: rotas de anexos; `cadastros_products.py`: rotas de foto; novo `routers/members.py`.
- `pages/tickets/TicketDetailPage.tsx`: card de anexos real; `TicketCreatePage.tsx` e `ActionPanel.tsx`: seletor de supervisor.
- `docker-compose.yml`, `dev.ps1`, `backend/pyproject.toml` (boto3, Pillow), `README.md`.
