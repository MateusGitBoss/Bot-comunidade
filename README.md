# bot-comunidade

[![CI](https://github.com/MateusGitBoss/Bot-comunidade/actions/workflows/ci.yml/badge.svg)](https://github.com/MateusGitBoss/Bot-comunidade/actions/workflows/ci.yml)

Bot de Discord para a comunidade de alunos de uma escola de cursos online. Responde dúvidas com IA usando só a base de FAQ da empresa e mostra ao aluno, em mensagem privada, se a compra dele foi aprovada.

**Para quem não é técnico:** é um atendente dentro do Discord que conhece as regras da escola (acesso, pagamento, reembolso, certificado). Quando a dúvida está nas regras, ele responde na hora; quando não está, ele avisa que vai passar para a equipe e manda a pergunta para o canal de suporte, em vez de inventar. O aluno também pode digitar o e-mail da compra para saber se o pagamento foi aprovado, e só ele vê a resposta.

## Fluxo

```mermaid
flowchart LR
    A[Aluno no Discord] -->|/pergunta| B[Busca BM25 na FAQ<br/>docs/faq/*.md]
    B -->|nenhum trecho relevante| E[Encaminha para #suporte-humano]
    B -->|3 trechos| C[Claude Haiku<br/>prompt + trechos]
    C -->|respondida=true| D[Resposta + botões 👍 👎]
    C -->|respondida=false / recusa| E
    D --> F[(Postgres<br/>interacoes)]
    E --> F
    A -->|/status-compra| G[API webhook-vendas<br/>POST /vendas/consulta-status]
    G -->|resposta efêmera| A
```

## Comandos

| Comando | Quem usa | O que faz |
|---|---|---|
| `/pergunta texto` | todos | Responde com base na FAQ; sem base, encaminha para o suporte |
| `/status-compra email` | todos | Status das compras daquele e-mail (só o aluno vê) |
| `/ping` | todos | Confere se o bot está no ar |
| `/faq-recarregar` | quem pode gerenciar o servidor | Relê `docs/faq/` sem reiniciar o bot |
| `/uso-hoje` | quem pode gerenciar o servidor | Perguntas, feedback e custo estimado do dia |

## Como a IA é impedida de inventar

1. **Contexto restrito.** O modelo recebe só os 3 trechos da FAQ mais parecidos com a pergunta, e o prompt (`prompts/sistema.md`) manda usar somente eles.
2. **Sem trecho, sem chamada.** Se a busca não acha nada relevante, a API nem é chamada: a pergunta vai direto para uma pessoa.
3. **Saída estruturada.** A API devolve sempre um JSON `{respondida, resposta}` (structured outputs). `respondida=false`, recusa do filtro de segurança, JSON cortado ou resposta vazia viram "encaminhar para a equipe".
4. **Medição.** Cada resposta tem botões 👍 👎 e tudo fica gravado. `docs/consultas.sql` mostra o que a base não cobre e quais trechos geram resposta ruim.
5. **Injeção de prompt.** A pergunta do aluno vai dentro de `<pergunta>`, sem `<` e `>`, e o prompt manda tratá-la só como pergunta.

## Custo

Modelo padrão: `claude-haiku-5-5` (US$ 0,10 por milhão de tokens de entrada e US$ 0,50 de saída, na tabela usada em `ia.py`). Uma pergunta típica usa uns 600 tokens de entrada e menos de 200 de saída: algo como US$ 0,0002, ou seja, cerca de 2 centavos de dólar a cada 100 perguntas (estimativa; o custo real de cada chamada fica gravado em `interacoes.custo_usd`). Proteções: limite de perguntas por usuário por hora (`LIMITE_PERGUNTAS_HORA`), `effort` baixo, pergunta cortada em 500 caracteres e nenhuma chamada quando a base não cobre o assunto.

## Como rodar

Pré-requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/), Postgres, um bot criado no [Discord Developer Portal](https://discord.com/developers/applications) e uma chave da API da Anthropic.

```bash
cp .env.example .env        # preencha DISCORD_TOKEN, ANTHROPIC_API_KEY, HASH_SEGREDO...
uv sync
uv run bot                  # aplica as migrações e conecta no Discord
```

Com Docker (Postgres incluso): `docker compose up --build`.

Para os comandos aparecerem na hora durante o desenvolvimento, preencha `DISCORD_GUILD_ID` com o ID do seu servidor de testes. Sem ele, o Discord pode levar até 1 hora para mostrar comandos novos.

Convite do bot: no Developer Portal, em OAuth2 > URL Generator, marque os escopos `bot` e `applications.commands` e a permissão "Send Messages".

### Testes e qualidade

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
DATABASE_URL_TESTE=postgresql://postgres:postgres@localhost:5432/bot_teste uv run pytest
```

Nenhum teste chama o Discord ou a API do Claude: as duas são substituídas por dublês (`tests/fakes.py`). Os testes do repositório rodam contra Postgres de verdade (service container no CI).

## Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `DISCORD_TOKEN` | Token do bot (Developer Portal > Bot) |
| `DISCORD_GUILD_ID` | Opcional: servidor onde os comandos aparecem na hora |
| `CANAL_SUPORTE_ID` | Opcional: canal que recebe as perguntas sem resposta |
| `ANTHROPIC_API_KEY` | Chave da API do Claude |
| `MODELO` | Padrão `claude-haiku-5-5` |
| `DATABASE_URL` | Postgres (no Supabase, use a URL do session pooler) |
| `HASH_SEGREDO` | Segredo do HMAC que esconde o ID do Discord no banco |
| `LIMITE_PERGUNTAS_HORA` | Padrão 10 |
| `VENDAS_API_URL` / `VENDAS_API_TOKEN` | API do [webhook-vendas](https://github.com/MateusGitBoss/webhook-vendas) e o mesmo `API_TOKEN` configurado lá |

## Deploy no Railway

1. New Project > Deploy from GitHub repo > este repositório. O `railway.json` manda usar o `Dockerfile`.
2. Em Variables, preencha as variáveis acima (Postgres pode ser o plugin do Railway ou o Supabase).
3. O bot não recebe HTTP, então não precisa de domínio público. O Railway reinicia o processo se ele cair.

## Decisões técnicas

- **BM25 em vez de banco vetorial.** A FAQ tem dezenas de trechos. BM25 roda em memória, não tem custo de embeddings nem serviço extra, e dá para explicar por que um trecho foi escolhido. Limitação: não entende sinônimos ("live" só acha "aula ao vivo" porque a FAQ cita as duas palavras). Se a base crescer muito, o próximo passo seria busca híbrida com embeddings.
- **Haiku com `effort` baixo.** A tarefa é reescrever um trecho curto em linguagem simples, não raciocinar. Modelo maior custaria mais sem ganho visível.
- **Regras fora do Discord.** `servico.py` não importa nada do Discord; `discord_app.py` só traduz comandos. Assim os testes cobrem a regra sem conectar em nada, e trocar Discord por Telegram mexeria só numa camada.
- **SQL à mão com psycopg assíncrono.** Uma tabela só; ORM seria peso extra. O pool de conexões evita abrir conexão a cada pergunta.
- **Prompt em arquivo versionado.** Mudança de prompt passa por PR, com histórico e revisão, sem tocar em código.

## Dados pessoais (LGPD)

O ID do Discord é gravado como HMAC-SHA256 (`usuario_hash`): dá para contar perguntas por usuário sem saber quem é. O e-mail de `/status-compra` não é gravado aqui; vai no corpo do POST (não na URL, que acaba em log) e a resposta é efêmera.

## Limitações conhecidas

- O limite por hora fica em memória: zera se o bot reiniciar e não vale para duas instâncias ao mesmo tempo.
- Os botões de feedback param de funcionar depois de 1 hora ou de um reinício do bot.
- `/status-compra` confia no e-mail digitado: qualquer um que saiba o e-mail de outra pessoa vê o status da compra dela (sem dados de pagamento). Uma versão real deveria vincular a conta do Discord ao e-mail com verificação.
- WhatsApp ficou fora: a API oficial exige conta business verificada na Meta, e as alternativas não oficiais correm risco de banimento do número.

## Como este projeto foi construído

Construído com o Claude Code como ferramenta de desenvolvimento, com cada mudança entrando por pull request. O roteiro de estudo em [`docs/ENTREVISTA.md`](docs/ENTREVISTA.md) explica cada decisão.

## Licença

MIT
