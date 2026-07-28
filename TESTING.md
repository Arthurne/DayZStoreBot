# DayZStoreBot — Guia de Testes e Instalação (versão atual)

Este documento fecha a validação da versão atual do bot (Etapas 1–7) antes
da Etapa 8. Cobre instalação local, configuração, execução, um roteiro de
teste ponta a ponta, teste de persistência após restart, e os erros mais
prováveis com a solução.

> **O que já foi validado nesta rodada** (sem rodar o bot de verdade — sem
> rede neste ambiente de desenvolvimento): sintaxe de todos os arquivos
> (`py_compile`), grafo de imports (zero ciclos a nível de módulo — os
> pontos de acoplamento circular são resolvidos com import tardio dentro de
> função), variáveis de `.env` batendo 100% com `config.py` e o código,
> `requirements.txt` batendo 100% com os imports reais do projeto, e testes
> unitários isolados do parser de preço e do slugify de categoria — que
> revelaram e corrigiram **2 bugs reais**: preço negativo era aceito, e
> cancelamento de pedido já ENTREGUE não era bloqueado. Ambos corrigidos.
> Tudo o que segue abaixo **precisa ser confirmado rodando o bot de
> verdade** — nenhuma checagem estática substitui isso.

---

## 1. Como instalar localmente

```bash
git clone <seu-repositório>   # ou copie a pasta DayZStoreBot/
cd DayZStoreBot

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Dependências instaladas: `discord.py`, `SQLAlchemy` (async), `aiosqlite`,
`python-dotenv`, `httpx`, `fastapi`, `uvicorn`.

---

## 2. Como configurar o `.env`

```bash
cp .env.example .env
```

Preencha cada campo:

| Variável | Onde conseguir | Obrigatória |
|---|---|---|
| `DISCORD_TOKEN` | [Discord Developer Portal](https://discord.com/developers/applications) → sua aplicação → Bot → Reset Token | ✅ |
| `GUILD_ID` | Discord → clique direito no ícone do servidor com o Modo Desenvolvedor ativo → "Copiar ID do Servidor" | ✅ |
| `STEAM_API_KEY` | https://steamcommunity.com/dev/apikey | ✅ |
| `STEAM_OPENID_REALM` | URL pública do seu servidor web (ex: `https://seubot.exemplo.com` ou um túnel ngrok em dev) | ✅ |
| `STEAM_OPENID_RETURN_URL` | Igual acima + `/steam/callback` (ex: `https://seubot.exemplo.com/steam/callback`) | ✅ |
| `WEB_HOST` / `WEB_PORT` | Padrão `0.0.0.0` / `8000` — só mude se precisar | Não |
| `DATABASE_URL` | Padrão SQLite local (`sqlite+aiosqlite:///./dayz_store.db`) — troque só ao migrar pra PostgreSQL | Não |
| `LOG_LEVEL` | Padrão `INFO`; use `DEBUG` pra investigar problema | Não |

⚠️ **A Steam exige HTTPS** no `openid.realm` fora de `localhost`. Em
desenvolvimento local, use um túnel (ex: `ngrok http 8000`) e copie a URL
gerada para `STEAM_OPENID_REALM`/`RETURN_URL` — `http://localhost` não
funciona com o login da Steam.

`config.py` falha alto (mensagem clara) se qualquer variável obrigatória
estiver vazia — não há como o bot subir "quebrado silenciosamente" por
`.env` incompleto.

---

## 3. Como iniciar o bot

```bash
python main.py
```

O que acontece, em ordem:
1. Configura logging (nível vindo de `LOG_LEVEL`).
2. Cria as tabelas do banco se não existirem (`init_db()`).
3. Carrega todos os cogs de `commands/` automaticamente.
4. Registra as views persistentes (Steam, Minhas Entregas, botões de
   Comprar de produtos ativos, aprovações de pagamento pendentes).
5. Sincroniza os slash commands **só no `GUILD_ID` configurado**.
6. Sobe o bot Discord **e** o servidor web (callback Steam) juntos, no
   mesmo processo — você verá logs de ambos no mesmo terminal.

Log de sucesso esperado:
```
INFO ... Bot conectado como <nome>#<tag> (id=...) — 1 servidor(es), N comando(s) sincronizado(s) localmente.
INFO ... Uvicorn running on http://0.0.0.0:8000
```

---

## 4. Permissões necessárias no Discord

### No convite do bot (OAuth2 URL Generator)
- Escopos: `bot` + `applications.commands`
- Permissões: **Gerenciar Canais**, **Gerenciar Apelidos**, **Ver Canais**,
  **Enviar Mensagens**, **Inserir Links** (embeds), **Ler Histórico de
  Mensagens**

### No Developer Portal da aplicação
- [ ] **SERVER MEMBERS INTENT** ligado (aba Bot) — sem isso a conexão
      falha ou membros não são resolvidos corretamente.

### No servidor, depois de convidado
- [ ] Cargo do bot movido **acima** dos cargos dos jogadores comuns na
      lista de cargos (senão `Gerenciar Apelidos` não funciona nos
      jogadores, mesmo com a permissão concedida — é hierarquia, não
      permissão).
- [ ] Nenhuma permissão adicional de "Administrador" é necessária pro bot
      em si — quem precisa ser Administrador no servidor são os **humanos**
      que vão usar `/setup`-like commands (o bot checa
      `member.guild_permissions.administrator` do usuário que roda o
      comando, não do bot).

> Limitação inerente do Discord (não é bug): o bot **nunca** consegue
> alterar o apelido do **dono do servidor**, não importa a hierarquia de
> cargos. Se você testar logando com a conta dona do servidor, o apelido
> não vai mudar — teste a troca de apelido com uma conta secundária.

---

## 5. Teste completo (ponta a ponta)

Recomendo testar nesta ordem, num servidor de testes real:

### 5.1 Cadastro Steam
1. Confirme que o canal `🎮・registro` foi criado automaticamente ao subir
   o bot.
2. Com uma conta **que não seja a dona do servidor**, clique em
   **🔗 Conectar Steam**.
3. Faça login na Steam quando o navegador abrir.
4. Confirme: página de sucesso no navegador, mensagem de confirmação no
   Discord, e **apelido trocado** para o nome da Steam.
5. Clique em **Conectar Steam** de novo — deve mostrar
   `ℹ Você já está vinculado como <nome>` em vez de repetir o fluxo.

### 5.2 Criação de produto
1. Rode `/produto criar` (precisa ser Administrator).
2. Preencha o modal 1/2 (Nome, Descrição, Preço, Categoria) e confirme.
3. Preencha o modal 2/2 (Itens da entrega, Imagem) e confirme.
4. Confirme que apareceu a categoria `📁 LOJA DAYZ` com um subcanal
   nomeado conforme a categoria digitada (ex: `🔫・armas`), e a mensagem do
   produto com o botão **🛒 Comprar**.
5. Teste também `/produto editar <nome>`, `/produto desativar <nome>` e
   `/produtos` (lista com dropdown).

### 5.3 Compra
1. Com a conta já vinculada à Steam, clique em **🛒 Comprar**.
2. Confirme o embed **CONFIRMAR COMPRA** com Produto/Valor/Steam corretos.
3. Clique em **Confirmar**.
4. Confirme: mensagem de sucesso com o número do pedido, canal privado
   `pedido-<id>-<nome>` criado (visível só pra você + admins), e um evento
   **🛒 NOVA COMPRA** postado em `📜・logs-vendas`.
5. **Teste o clique duplicado**: clique em Comprar duas vezes rápido antes
   de confirmar a primeira — a segunda deve avisar que já existe uma
   compra pendente, não criar um segundo pedido.

### 5.4 Aprovação de pagamento
1. Entre no canal privado do pedido (como admin).
2. Clique em **Aprovar Pagamento**.
3. Confirme: status muda pra PAGO, os botões da mensagem ficam
   desabilitados, e uma `Delivery` é criada automaticamente.

### 5.5 Entrega
1. Rode `/entregas` (admin).
2. Selecione o pedido no dropdown e processe (Processando → Entregue).
3. Confirme que o status também mudou no canal privado do pedido.
4. Como o jogador, vá em `📦・entregas` → **Minhas Entregas** e confirme
   que a entrega aparece com status atualizado.
5. **Teste o bloqueio de cancelamento**: tente cancelar esse mesmo pedido
   (já ENTREGUE) — deve recusar com
   `⚠ Não foi possível cancelar (pedido não existe ou já foi entregue)`.

---

## 6. Teste após reiniciar o bot

Este teste é essencial — views "esquecidas" depois de um restart é a causa
mais comum de bot Discord parecer quebrado sem estar.

1. Com o bot rodando e pelo menos **1 produto ativo** e **1 pedido
   PENDENTE** (ainda não aprovado) no banco, **pare o bot** (`Ctrl+C`).
2. Suba de novo (`python main.py`).
3. **Botões persistentes**: sem rodar nenhum comando novo, clique no botão
   **🛒 Comprar** de um produto criado antes do restart — deve responder
   normalmente, não deve dar "This interaction failed".
4. Clique em **Aprovar Pagamento** no canal do pedido que ficou PENDENTE
   antes do restart — deve funcionar também.
5. Clique em **🔗 Conectar Steam** e em **Minhas Entregas** — ambos devem
   continuar respondendo (views estáticas, sempre registradas).
6. **Mensagens da loja**: confirme que as mensagens de produto antigas
   continuam com o embed correto (não duplicaram, não sumiram). Edite um
   produto (`/produto editar`) depois do restart e confirme que a mensagem
   existente foi **editada no lugar**, não duplicada.

Se qualquer botão responder "This interaction failed" ou não responder
nada depois do restart, o problema está em `main.py::setup_hook` não
registrar aquela view a tempo — confira os logs de startup por erros nas
linhas de `register_persistent_*`.

---

## 7. Possíveis erros e soluções

| Sintoma | Causa provável | Solução |
|---|---|---|
| Bot não conecta, erro `Improper token` | `DISCORD_TOKEN` errado/expirado | Gere um novo token no Developer Portal e atualize o `.env` |
| Bot conecta mas comandos não aparecem no Discord | `GUILD_ID` errado, ou você está testando em outro servidor | Confirme o ID copiado é do servidor certo; o bot sincroniza **só** nesse servidor |
| Bot entra e sai sozinho de um servidor com um aviso | Proteção de servidor autorizado — o `GUILD_ID` do `.env` não bate com o servidor onde o bot foi adicionado | Isso é esperado (Etapa 3): o bot só funciona no `GUILD_ID` configurado |
| `RuntimeError: Variável de ambiente obrigatória '...' não encontrada` | `.env` incompleto | Confira contra `.env.example`, todos os campos marcados obrigatórios na seção 2 |
| Apelido não muda mesmo sem erro aparente | Conta testada é a **dona do servidor** | Teste com uma conta secundária — limitação do Discord, não do bot |
| Erro `Forbidden` ao trocar apelido / criar canal | Cargo do bot abaixo do cargo do usuário, ou falta permissão | Mova o cargo do bot pra cima na hierarquia; confirme as permissões da seção 4 |
| Login da Steam falha ou não redireciona de volta | `STEAM_OPENID_REALM`/`RETURN_URL` incorretos, ou usando `http://localhost` | Use HTTPS público (ngrok em dev); confirme que a URL de retorno bate exatamente com o que está no `.env` |
| "Perfil Steam indisponível" depois do login | Perfil da Steam do jogador está **privado** | Peça pro jogador deixar o perfil público (Configurações de Privacidade da Steam) |
| Botão responde "This interaction failed" só depois de reiniciar o bot | View persistente não foi re-registrada no `setup_hook` | Ver seção 6 — confira logs de `register_persistent_buy_views`/`register_persistent_approval_views` |
| `sqlite3.OperationalError: database is locked` | Múltiplas instâncias do bot rodando ao mesmo tempo no mesmo `dayz_store.db` | Rode só uma instância por banco; para produção com mais tráfego, migre `DATABASE_URL` pra PostgreSQL |
| Produto criado mas mensagem não aparece no canal | Bot sem permissão de **Enviar Mensagens** no canal recém-criado (raro, geralmente herda da categoria) | Confira as permissões da categoria `📁 LOJA DAYZ` |
| `ModuleNotFoundError` ao rodar `python main.py` | `pip install -r requirements.txt` não rodou, ou venv errado ativado | Reative o venv certo e reinstale |

---

## Resumo do estado atual

Etapas 1 a 7 implementadas e revisadas (2 bugs corrigidos nesta rodada:
preço negativo aceito, e cancelamento de pedido já entregue não bloqueado).
Nenhuma funcionalidade nova foi adicionada neste documento — é só a
consolidação da documentação de teste da versão atual, como pedido.
