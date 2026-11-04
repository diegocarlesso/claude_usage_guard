---
name: ferramentas-do-projeto
description: Use quando o usuário pedir para sugerir, instalar ou revisar skills, MCPs, plugins ou hooks do projeto, ou ao ver um pedido "[usage-guard]" do botão "Skills/MCPs" do Claude Usage Guard. Diz como descobrir o stack gastando pouco, o que propor (pôr e tirar) e como instalar só o que o usuário aprovar.
---

# Ferramentas do projeto

Objetivo: deixar a sessão com as ferramentas certas para este projeto e **sem peso morto**. Cada skill, MCP ou
plugin ativo põe texto no contexto de toda sessão (a descrição da skill, as definições das ferramentas do MCP).
Ferramenta sem uso custa tokens em todo turno; ferramenta que falta custa retrabalho.

Trabalhe em passos curtos e pare para o usuário aprovar antes de instalar ou remover qualquer coisa.

## 1. Descobrir o stack gastando pouco

Delegue a um subagente com `model: haiku` e peça só a conclusão (até 15 linhas):

- manifestos na raiz e um nível abaixo: `package.json`, `pyproject.toml`, `requirements*.txt`, `*.csproj`,
  `go.mod`, `Cargo.toml`, `pom.xml`, `Gemfile`, `composer.json`, `Dockerfile`;
- as primeiras 40 linhas do `README`, o `CLAUDE.md` e a pasta `.claude/` (se existirem);
- linguagem, frameworks, banco de dados, testes, build, nuvem e serviços externos citados.

Não leia o código inteiro. Se o stack já estiver claro no contexto, pule este passo.

## 2. Inventário do que já está ativo

- **Skills:** a lista com nomes e descrições já está no seu contexto. Separe as globais (`~/.claude/skills/`) das
  do projeto (`.claude/skills/`) e das de plugins.
- **MCPs e conectores:** as ferramentas `mcp__*` do seu contexto; `.mcp.json` do projeto.
- **Plugins:** os que aparecem como prefixo `plugin:` nas skills e nos MCPs.
- **Hooks:** `.claude/settings.json` do projeto e `~/.claude/settings.json` (só leia; os hooks com
  `claude_usage_guard` e `desktop-hook` são do Claude Usage Guard e não devem ser tocados).

Conte quantas skills e MCPs estão ativos. Mais de ~50 skills ou MCPs com dezenas de ferramentas já pesam no
contexto de toda sessão.

## 3. Proposta

Monte uma tabela curta, em duas partes:

**Pôr (até 5):** o que falta para o stack e para o jeito de trabalhar do usuário (ex.: MCP do banco usado, skill de
testes do framework, hook de formatação).

**Tirar ou desligar (até 5):** o que não tem relação com o projeto ou se repete (ex.: dezenas de skills de outra
área instaladas globalmente, MCPs de serviços que o projeto não usa, plugins duplicados).

| Item | Pôr/Tirar | Para quê | Custo em contexto | Como |
|---|---|---|---|---|

Seja concreto no custo: "~60 tokens por skill em toda sessão", "~2k tokens de definições de ferramentas".

## 4. Onde procurar o que pôr

1. Primeiro as ferramentas do próprio app, se estiverem disponíveis na sessão: `SearchPlugins`, `SuggestSkills`,
   `SuggestPluginInstall`, busca no registro de MCP (`search_mcp_registry`, `suggest_connectors`).
2. Senão, fontes oficiais: marketplace de plugins da Anthropic, registro oficial de MCP, repositório do
   fornecedor do serviço.
3. Antes de dizer como instalar, confira na documentação atual: comandos e formatos mudam.

Prefira itens oficiais ou muito usados. Desconfie de MCPs que pedem credenciais amplas.

## 5. Instalar ou remover, só com aprovação

- Pergunte item por item (ou "todos os da tabela"). Sem resposta clara, não instale.
- Prefira o escopo do **projeto**: skills em `.claude/skills/<nome>/SKILL.md`, MCPs no `.mcp.json`, hooks no
  `.claude/settings.json`. Assim o resto dos projetos não muda.
- Para **tirar** algo global (`~/.claude/skills/`, plugins, MCPs do usuário), explique que afeta todos os projetos
  e proponha a alternativa: mover para o `.claude/skills/` dos projetos que usam, ou desativar em vez de apagar.
  Nunca apague sem confirmação explícita; prefira mover para uma pasta de backup.
- Skill nova feita por você: curta (até ~80 linhas), com `name` e `description` que digam quando usar.
- Credenciais (tokens, chaves) o usuário digita; você não as inventa nem grava em arquivo versionado.
- Nunca altere os hooks do Claude Usage Guard nem o `"model"` do `settings.json`.

## 6. Fechamento

Diga em 3 a 5 linhas o que mudou, o que ficou para depois e se é preciso abrir uma sessão nova para valer
(skills e MCPs novos costumam aparecer só em sessões novas).
