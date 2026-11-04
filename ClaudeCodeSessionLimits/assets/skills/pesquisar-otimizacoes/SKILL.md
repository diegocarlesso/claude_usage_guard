---
name: pesquisar-otimizacoes
description: Use quando o usuário pedir para pesquisar boas práticas ou otimizações para o projeto ou para o uso do Claude Code nele, ou ao ver um pedido "[usage-guard]" do botão "Pesquisar" do Claude Usage Guard. Diz como pesquisar gastando pouco, onde gravar o resultado e como aplicar só o que o usuário aprovar.
---

# Pesquisar otimizações

Objetivo: achar as mudanças de **maior ganho** para este projeto, nesta ordem de prioridade:

1. **Uso do Claude Code neste projeto gastando menos cota** e com melhores resultados: `CLAUDE.md`, skills, hooks,
   escolha de modelos e subagentes, fluxo de trabalho (planejar antes, `/compact` e `/clear`, testes).
2. **Boas práticas e otimizações do stack**: linguagem, frameworks, build, testes, desempenho, segurança.

Pesquisar custa cota (cada resultado de busca entra no contexto). Siga os passos para gastar o mínimo.

## 1. Já existe uma pesquisa recente?

Se houver `OTIMIZACOES.md` na raiz do projeto com data de menos de 30 dias:

- leia só a tabela de achados e mostre ao usuário o que ainda não foi aplicado;
- pergunte se quer pesquisar de novo ou aplicar o que já está lá. Sem resposta, não pesquise.

## 2. Contexto curto

Em até 10 linhas, para passar ao subagente:

- stack (manifestos, começo do `README`; se não estiver claro, um subagente `model: haiku` descobre);
- como o usuário trabalha: `CLAUDE.md`, `.claude/` (skills, hooks), tamanho do projeto;
- o que já foi aplicado (coluna "aplicado?" do `OTIMIZACOES.md`, se existir).

## 3. Pesquisa delegada

Chame **um** subagente com `model: sonnet` e estas regras no pedido:

- no máximo 6 buscas na web; prefira documentação oficial, changelogs e fontes com data;
- primeiro o tema 1 (uso do Claude Code), depois o tema 2 (stack);
- resposta com no máximo 400 palavras: achados em tópicos, cada um com ganho estimado (alto/médio/baixo),
  custo de aplicar e link da fonte;
- nada de copiar trechos longos das páginas.

Não faça buscas você mesmo em paralelo ao subagente.

## 4. Gravar `OTIMIZACOES.md`

Na raiz do projeto. Se o arquivo já existir, acrescente uma seção nova com a data no topo; não apague as antigas.

```markdown
# Otimizações — <AAAA-MM-DD>

## Achados
| # | Tema | Mudança | Ganho | Custo | Aplicado? | Fonte |
|---|---|---|---|---|---|---|
| 1 | Claude Code | ... | alto | baixo | não | <link> |

## Notas
- <contexto que explica um achado, se precisar>
```

Ordene a tabela por ganho (alto primeiro). Use frases curtas.

## 5. Propor e aplicar com aprovação

- No chat, mostre só as **3 a 5 mudanças de maior ganho**: o que muda, ganho, custo e risco, numa linha cada.
- Pergunte quais aplicar. Aplique só as aprovadas, uma por vez, conferindo o resultado (testes, build).
- Marque "sim" na coluna "Aplicado?" das que aplicou.
- Mudanças de configuração global (`~/.claude/`) afetam todos os projetos: diga isso antes.
- Nunca altere os hooks do Claude Usage Guard nem o `"model"` do `settings.json`.

## 6. Fechamento

Em 3 linhas: o que foi aplicado, o que ficou no `OTIMIZACOES.md` para depois e quando vale pesquisar de novo
(mudança grande no stack ou daqui a um mês).
