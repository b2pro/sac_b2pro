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

## CORS do bucket (obrigatório em produção)

O navegador envia o PUT direto para o bucket com um `Content-Type` explícito, o que é um pedido **cross-origin com header não simples** — o browser dispara um preflight `OPTIONS` antes do PUT. O MinIO usado em desenvolvimento libera isso por padrão, então **nenhum teste local detecta a falta desta configuração**; o Wasabi **não** libera: sem uma política de CORS no bucket o preflight é recusado e o upload falha no navegador com um erro opaco (`xhr.onerror`, sem status).

Aplicar no bucket (`PutBucketCors`, via console do Wasabi ou `aws s3api put-bucket-cors --endpoint-url https://s3.<regiao>.wasabisys.com --bucket <bucket> --cors-configuration file://cors.json`):

```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["https://sac.b2pro.com.br"],
      "AllowedMethods": ["PUT", "GET", "HEAD"],
      "AllowedHeaders": ["Content-Type", "x-amz-*", "Authorization"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
```

- `AllowedOrigins`: a origem exata do frontend (uma entrada por ambiente; nunca `*` em produção, para não transformar URLs assinadas vazadas em upload de qualquer site).
- `AllowedMethods`: `PUT` para o upload direto, `GET`/`HEAD` para o download e o preview por presigned GET.
- `AllowedHeaders` precisa conter `Content-Type` — é justamente esse header que força o preflight (ver `putToStorage` em `frontend/src/lib/attachments.ts`).

## Limite de tamanho: o que é garantido e o que não é

Risco aceito e consciente: uma **presigned URL de `put_object` não suporta `content-length-range`** (isso é recurso de POST policy). Quem tem a URL assinada pode gravar mais bytes do que declarou na intenção, durante todo o TTL (300 s).

- O que protege: a intenção valida o tamanho declarado (`validate_size`), a confirmação faz `HEAD` no objeto e **recusa** tamanho/tipo divergentes, o anexo não confirmado expira em 30 min e a URL é curta e emitida só para usuário autenticado com permissão no ticket.
- O que não é evitado: o objeto grande **já foi gravado** e permanece no bucket, ocupando custo, mesmo com a confirmação recusada. Por isso `StoragePort.presigned_put` **não** recebe `max_bytes` — um parâmetro assim seria ignorado em silêncio e prometeria uma garantia inexistente.
- Mitigação obrigatória (configuração de bucket, não de código): **regra de ciclo de vida** que expira objetos nunca confirmados. Como as chaves nascem sob `{tenant}/{ticket}/…` e `{tenant}/catalogo/produtos/…`, a regra prática é expirar objetos com mais de 1 dia que não tenham anexo confirmado — na configuração do bucket, uma regra por prefixo com `Expiration: Days: 1` sobre um prefixo dedicado de staging, ou uma varredura periódica que compare o bucket com as chaves confirmadas no banco.
- Se um dia o upload migrar para **POST policy**, o `content-length-range` passa a ser aplicado no próprio storage e este risco desaparece (mudança de fase, não de correção pontual).

## Antes do primeiro deploy em produção

Checklist do que **não** é verificável localmente (o MinIO é permissivo onde o Wasabi não é):

1. **CORS do bucket** aplicado com a origem real do frontend (seção acima). Sem isso todo upload pelo navegador falha.
2. **Bucket privado**: nenhum acesso público de leitura/escrita, nenhuma política anônima; credenciais com IAM policy restrita ao bucket/prefixo. Todo acesso é por URL assinada de TTL curto.
3. **Regra de ciclo de vida** para objetos nunca confirmados (seção acima), que é o que mitiga o limite de tamanho não aplicável no PUT assinado.
4. `SAC_S3_PUBLIC_ENDPOINT_URL` apontando para o endpoint que o **navegador** alcança: a assinatura cobre o header `Host`, então trocar o host depois de assinar invalida a URL.

## Previews (thumbnails)

- Gerados por um **worker em background bem limitado** (fila com concorrência baixa e limites de CPU/memória — imagem grande não pode derrubar a API): baixa o original, gera thumbnail (ex.: WebP ~400px) e um tamanho médio para o lightbox, grava em `{tenant}/{ticket}/previews/{uuid}.webp`.
- Estados do preview no anexo: `sem_preview` (PDF/vídeo), `pendente`, `pronto`, `falhou` (galeria mostra placeholder e o job pode reprocessar).
- Job idempotente e com retry/backoff.

## Galeria de mídias (paridade com o legado, melhorada)

- Tela "Mídias" com filtros: tipo (imagem/PDF), produto, defeito, solução, status do ticket, período.
- O grid carrega **apenas os previews** (nunca os originais) — presigned GETs dos thumbnails, com lazy loading.
- Clique abre lightbox com o tamanho médio/original via presigned GET; PDF abre em nova aba/inline viewer.
- Cada card liga ao ticket de origem (número, produto, chips de defeito/solução), como no legado.
