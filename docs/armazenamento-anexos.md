# Armazenamento de anexos — Wasabi S3

Anexos de tickets (principalmente **imagens e PDFs**) ficam no **Wasabi** (object storage 100% compatível com a API S3 — usamos boto3/SDK S3 apontando para o endpoint do Wasabi). Docs: https://docs.wasabi.com/apidocs/wasabi-api

Fato verificado (2026-07): o Wasabi suporta presigned URLs, mas **não possui processamento nativo de imagem nem geração de thumbnails** — é storage puro. Portanto os previews são gerados por um job nosso.

## Regras por tipo

- **PDF**: salvo como está, sem transformação. Na galeria aparece com ícone/placeholder de documento.
- **Imagem** (jpg/png/webp): comprimida quando passar de um limite configurável (ex.: `ATTACHMENT_IMAGE_MAX_BYTES`, `ATTACHMENT_IMAGE_MAX_DIMENSION`). A compressão acontece **no client antes do upload** (canvas/WASM, já que o upload é direto para o Wasabi) e o worker valida/normaliza depois; imagens que ainda cheguem grandes são recomprimidas pelo job.

## Fluxo de upload (direto para o Wasabi, com URL assinada)

O arquivo **nunca passa pelo backend**. Boas práticas de segurança obrigatórias:

1. Client pede ao backend a intenção de upload (`ticket_id`, nome, mime, tamanho).
2. Backend valida (permissão no ticket, mime permitido, tamanho máximo, quota) e emite **presigned URL de PUT** (ou POST policy) com:
   - **chave gerada pelo servidor** (nunca escolhida pelo client): `{tenant}/{ticket}/{uuid}.{ext}`;
   - TTL curto (minutos);
   - restrição de `Content-Type` e `content-length-range`;
   - registro do anexo em estado `pendente`.
3. Client faz PUT direto no Wasabi.
4. Client confirma; backend faz `HEAD` no objeto para verificar existência, tamanho e mime reais, marca o anexo como `disponivel` e **enfileira o job de preview** (se imagem).
5. Anexos `pendentes` sem confirmação expiram e são limpos por rotina.

- Bucket **privado**, sem acesso público; credenciais com IAM policy restrita ao bucket/prefixo.
- **Download/visualização também por presigned GET** de TTL curto, emitido só após checagem de permissão (nunca URL fixa).
- Objetos nunca são servidos pelo backend (sem proxy de bytes), exceto se um dia for necessário watermark/auditoria.

## Previews (thumbnails)

- Gerados por um **worker em background bem limitado** (fila com concorrência baixa e limites de CPU/memória — imagem grande não pode derrubar a API): baixa o original, gera thumbnail (ex.: WebP ~400px) e um tamanho médio para o lightbox, grava em `{tenant}/{ticket}/previews/{uuid}.webp`.
- Estados do preview no anexo: `sem_preview` (PDF/vídeo), `pendente`, `pronto`, `falhou` (galeria mostra placeholder e o job pode reprocessar).
- Job idempotente e com retry/backoff.

## Galeria de mídias (paridade com o legado, melhorada)

- Tela "Mídias" com filtros: tipo (imagem/PDF), produto, defeito, solução, status do ticket, período.
- O grid carrega **apenas os previews** (nunca os originais) — presigned GETs dos thumbnails, com lazy loading.
- Clique abre lightbox com o tamanho médio/original via presigned GET; PDF abre em nova aba/inline viewer.
- Cada card liga ao ticket de origem (número, produto, chips de defeito/solução), como no legado.
