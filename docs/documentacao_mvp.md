# Sistema Financeiro da Casa — MVP

Documentação funcional e técnica da primeira versão.

> **Versão 1.1** — revisão do PDF original (`documentacao_mvp_sistema_financeiro_casa.pdf`).
> A partir de agora, este arquivo é a documentação oficial do projeto e evolui junto com o código.
> As mudanças em relação ao PDF estão listadas no [Histórico de revisões](#histórico-de-revisões).

---

## 1. Visão do projeto

O Sistema Financeiro da Casa é uma aplicação web desenvolvida em Python com Flask, com o objetivo de permitir o controle básico das finanças domésticas.

O sistema permite registrar receitas e despesas, organizar os lançamentos por categorias e visualizar um resumo financeiro do período.

A primeira versão é um MVP (Minimum Viable Product): terá somente as funcionalidades essenciais para que o sistema seja utilizado no dia a dia.

### Objetivos principais

- Registrar receitas.
- Registrar despesas.
- Organizar lançamentos por categoria.
- Consultar, editar e excluir lançamentos.
- Visualizar receitas, despesas e saldo.
- Filtrar informações por período.
- Utilizar banco de dados SQLite.
- Praticar Python, Flask e SQL durante o desenvolvimento.

## 2. Tecnologias

| Camada | Tecnologia | Papel |
|---|---|---|
| Backend | Python + Flask | Lógica da aplicação, rotas, processamento e comunicação com o banco |
| Banco de dados | SQLite | Simples, leve e sem necessidade de servidor |
| Frontend | HTML + CSS + Jinja2 | Telas; JavaScript apenas quando necessário |
| Controle de versão | Git + GitHub | Acompanhar a evolução do projeto |

## 3. Escopo do MVP

```
Sistema Financeiro
├── Dashboard
├── Lançamentos
│   ├── Novo lançamento
│   ├── Editar lançamento
│   └── Excluir lançamento
└── Categorias
    ├── Criar categoria
    ├── Listar categorias
    └── Excluir categoria (somente se não tiver lançamentos)
```

> "Configurações básicas", que constava no PDF, foi retirado do MVP por não ter sido definido. Pode voltar em uma versão futura.

## 4. Dashboard

A tela inicial apresenta uma visão rápida da situação financeira:

- total de receitas;
- total de despesas;
- saldo;
- total de lançamentos;
- despesas por categoria;
- últimos lançamentos.

**Período padrão:** o mês atual. O usuário pode escolher outro período.

```
┌─────────────────────────────────────────────┐
│               FINANÇAS DA CASA              │
├──────────────┬──────────────┬───────────────┤
│   RECEITAS   │   DESPESAS   │     SALDO     │
│ R$ 5.000,00  │ R$ 3.200,00  │ R$ 1.800,00   │
└──────────────┴──────────────┴───────────────┘
```

## 5. Lançamentos

Cada lançamento possui: ID, descrição, valor, tipo (receita ou despesa), data, categoria, observação, data de criação e data da última atualização.

Exemplo (como o usuário vê):

```
Descrição:  Supermercado
Valor:      250,00
Tipo:       Despesa
Data:       05/10/2026
Categoria:  Alimentação
Observação: Compra da semana
```

O mesmo lançamento no banco:

```
descricao      = 'Supermercado'
valor_centavos = 25000
tipo           = 'despesa'
data           = '2026-10-05'
categoria_id   = 4
observacao     = 'Compra da semana'
```

## 6. Categorias

Categorias iniciais:

- **Receitas:** Salário, Freelance, Outros.
- **Despesas:** Alimentação, Moradia, Energia, Água, Internet, Transporte, Saúde, Educação, Lazer, Compras, Outros.

O usuário pode criar novas categorias.

**Exclusão:** uma categoria só pode ser excluída se nenhum lançamento a utilizar. Categorias em uso não podem ser excluídas.
(Futuro: permitir "inativar" uma categoria em vez de excluí-la.)

Não podem existir duas categorias com o mesmo nome e o mesmo tipo. "Outros" pode existir uma vez como receita e outra como despesa.

## 7. Banco de dados

O banco tem duas tabelas: `categorias` e `lancamentos`. Uma categoria pode possuir vários lançamentos (relacionamento 1:N).

### Tabela `categorias`

```sql
CREATE TABLE categorias (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT    NOT NULL,
    tipo TEXT    NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    UNIQUE (nome, tipo)
);
```

### Tabela `lancamentos`

```sql
CREATE TABLE lancamentos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao      TEXT    NOT NULL,
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
    tipo           TEXT    NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    data           TEXT    NOT NULL,              -- formato AAAA-MM-DD
    categoria_id   INTEGER NOT NULL,
    observacao     TEXT,
    criado_em      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE RESTRICT
);
```

### Decisões técnicas do banco

**Valores em centavos (INTEGER).**
O SQLite não tem um tipo `DECIMAL` exato: valores decimais são guardados como ponto flutuante, que gera erros de arredondamento (`0.1 + 0.2 = 0.30000000000000004`). Por isso, todo valor é guardado como **número inteiro de centavos**:

| Tela | Banco |
|---|---|
| R$ 250,00 | `25000` |
| R$ 5.000,00 | `500000` |
| R$ 0,99 | `99` |

A conversão acontece só na entrada (formulário → centavos) e na saída (centavos → tela).

**Valores sempre positivos.**
O valor nunca é negativo. Quem diz se o dinheiro entra ou sai é o campo `tipo`:

```
Receita: tipo = 'receita', valor_centavos = 500000
Despesa: tipo = 'despesa', valor_centavos = 35000
```

O `CHECK (valor_centavos > 0)` garante isso no próprio banco.

**Datas no formato ISO (`AAAA-MM-DD`).**
O banco guarda `2026-10-05` e a tela mostra `05/10/2026`. Nesse formato, a ordem alfabética coincide com a ordem cronológica, o que permite:

```sql
WHERE data BETWEEN '2026-10-01' AND '2026-10-31'
ORDER BY data DESC
```

**`criado_em` e `atualizado_em`.**
Os dois são preenchidos automaticamente na criação. Em toda edição, o `UPDATE` também atualiza `atualizado_em`:

```sql
UPDATE lancamentos
   SET descricao = ?, valor_centavos = ?, tipo = ?, data = ?,
       categoria_id = ?, observacao = ?,
       atualizado_em = CURRENT_TIMESTAMP
 WHERE id = ?;
```

> Observação: `CURRENT_TIMESTAMP` no SQLite grava o horário em **UTC** (3 horas a mais que o horário de Brasília). Para exibir, é preciso converter.

**Tipo guardado no lançamento e na categoria.**
O `tipo` existe nas duas tabelas, porque ele é uma característica do próprio lançamento. A regra é que **`lancamentos.tipo` deve ser igual a `categorias.tipo`**. Essa regra é validada no Python antes de salvar, e nunca depende só da interface:

```python
if lancamento_tipo != categoria_tipo:
    raise ValueError("O tipo do lançamento não corresponde à categoria.")
```

(Futuro: discutir uma modelagem em que essa inconsistência seja impossível no próprio banco.)

**Foreign keys ligadas na conexão.**
O SQLite vem com a verificação de foreign keys **desligada** por padrão, e ela precisa ser ativada **a cada conexão**. Por isso, toda conexão com o banco passa por uma única função:

```python
import sqlite3

def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row          # acessar colunas pelo nome: linha["descricao"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

Com isso, o `ON DELETE RESTRICT` passa a funcionar de verdade: o banco recusa a exclusão de uma categoria que tenha lançamentos.

## 8. Regras de negócio

1. O valor deve ser maior que zero (nunca negativo).
2. O tipo do lançamento determina se ele é receita ou despesa.
3. Todo lançamento deve possuir uma categoria.
4. O tipo do lançamento deve ser igual ao tipo da sua categoria (validado no Python).
5. Categorias em uso por algum lançamento não podem ser excluídas (verificado no Python, com o banco como segunda garantia).
6. Não podem existir duas categorias com o mesmo nome e tipo.
7. Toda edição de lançamento atualiza `atualizado_em`.

**Cálculo do saldo:**

```
SALDO = TOTAL DE RECEITAS − TOTAL DE DESPESAS
```

## 9. Operações CRUD

| Operação | Significado | SQL |
|---|---|---|
| Create | Cadastrar | `INSERT` |
| Read | Consultar | `SELECT` |
| Update | Editar | `UPDATE` |
| Delete | Excluir | `DELETE` |

## 10. Páginas da aplicação

| URL | Página |
|---|---|
| `/` | Dashboard |
| `/lancamentos` | Lista de lançamentos (com filtros) |
| `/lancamentos/novo` | Novo lançamento |
| `/lancamentos/editar/<id>` | Editar lançamento |
| `/categorias` | Lista de categorias |
| `/categorias/nova` | Nova categoria |

As exclusões não são páginas: são ações disparadas por um botão (formulário POST) nas listas.

## 11. Estrutura do projeto

```
A. Sistema Financeiro/
├── app.py
├── database.db              (gerado localmente, NÃO vai para o Git)
├── requirements.txt
├── README.md
├── .gitignore
├── docs/
│   ├── documentacao_mvp.md
│   └── documentacao_mvp_sistema_financeiro_casa.pdf   (versão original)
├── database/
│   └── schema.sql
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── lancamentos.html
│   ├── novo_lancamento.html
│   ├── editar_lancamento.html
│   ├── categorias.html
│   └── nova_categoria.html
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── script.js
```

## 12. Rotas do Flask

```
GET  /
GET  /lancamentos
GET  /lancamentos/novo
POST /lancamentos/novo
GET  /lancamentos/editar/<id>
POST /lancamentos/editar/<id>
POST /lancamentos/excluir/<id>
GET  /categorias
GET  /categorias/nova
POST /categorias/nova
POST /categorias/excluir/<id>
```

Toda ação que altera dados usa POST, nunca GET. Um link GET pode ser acionado sem querer, por exemplo pelo pré-carregamento do navegador.

## 13. Filtros

A tela de lançamentos permite filtrar por:

- período (data inicial e data final);
- tipo;
- categoria.

## 14. Relatórios iniciais

- Receitas x despesas.
- Despesas agrupadas por categoria.

Gráficos poderão ser adicionados depois.

## 15. O que NÃO faz parte do MVP

- Login e múltiplos usuários.
- Cartão de crédito e parcelamento.
- Contas bancárias e investimentos.
- Transferências entre contas.
- Importação de extrato e integração com bancos.
- Notificações e aplicativo mobile.
- Inteligência artificial.
- PostgreSQL e Docker.
- Deploy em produção.
- Configurações do sistema.
- Inativação de categorias.

## 16. Evolução futura

- **Versão 2:** contas bancárias, cartões, parcelas, despesas recorrentes, orçamento mensal, metas e categorias inativas.
- **Versão 3:** login, usuários, permissões, PostgreSQL, deploy e backup.
- **Versão 4:** API, aplicativo mobile, integração bancária, importação automática e notificações.

## 17. Ordem de desenvolvimento

| Etapa | Tema | Conteúdo |
|---|---|---|
| 1 | Preparação | Git, ambiente virtual, Flask, `requirements.txt`, pastas, "Olá, mundo" |
| 2 | Banco | `schema.sql`, função de conexão, tabelas e categorias iniciais |
| 3 | Primeiro CRUD | Criar e listar lançamentos |
| 4 | CRUD completo | Editar (com `atualizado_em`) e excluir |
| 5 | Categorias | Cadastro, listagem e exclusão protegida |
| 6 | Dashboard | Receitas, despesas, saldo e despesas por categoria |
| 7 | Filtros | Data, tipo e categoria |
| 8 | Melhorias visuais | Layout, menu, cards, tabelas, responsividade e gráficos |

## 18. Critério para considerar o MVP concluído

- [ ] Abrir o sistema.
- [ ] Cadastrar categoria.
- [ ] Excluir categoria sem uso, e ser impedido de excluir categoria em uso.
- [ ] Cadastrar receita.
- [ ] Cadastrar despesa.
- [ ] Ser impedido de salvar valor zero/negativo ou tipo diferente da categoria.
- [ ] Visualizar lançamentos.
- [ ] Editar lançamento (e ver `atualizado_em` mudar).
- [ ] Excluir lançamento.
- [ ] Filtrar lançamentos.
- [ ] Visualizar total de receitas.
- [ ] Visualizar total de despesas.
- [ ] Visualizar saldo.
- [ ] Visualizar despesas agrupadas por categoria.

## 19. Objetivo de aprendizado

- **Python:** funções, condições, módulos e tratamento de erros.
- **Flask:** rotas, views, templates, Jinja2, formulários, GET/POST.
- **SQL:** SELECT, INSERT, UPDATE, DELETE, WHERE, ORDER BY, GROUP BY, SUM, COUNT e JOIN.
- **Banco de dados:** modelagem, relacionamentos, restrições (`CHECK`, `UNIQUE`, `FOREIGN KEY`) e CRUD.
- **Git:** commits pequenos e frequentes, um por passo concluído.

## 20. Visão geral da arquitetura

```
              USUÁRIO
                 │
                 ↓
             NAVEGADOR
                 │
                 ↓
               FLASK
                 │
      ┌──────────┴──────────┐
      ↓                     ↓
    JINJA2                PYTHON
      │                     │
      ↓                     ↓
    HTML                   SQL
      │                     │
      └──────────┬──────────┘
                 ↓
               SQLITE
```

A aplicação roda localmente em `http://127.0.0.1:5000`.

## 21. Princípio principal

Criar uma aplicação pequena, funcional e organizada, e evoluí-la aos poucos, conforme novos conhecimentos forem adquiridos.

**Prioridade:** primeiro fazer funcionar → depois organizar → depois melhorar → depois expandir.

---

## Histórico de revisões

### v1.1 — 06/10/2026

- Valor passa a ser `valor_centavos INTEGER` (antes `DECIMAL(10,2)`), para evitar erros de arredondamento.
- `CHECK` no banco: valor > 0 e tipo em ('receita', 'despesa').
- `categoria_id` passa a ser `NOT NULL` (alinhado à regra "todo lançamento possui categoria").
- Novo campo `atualizado_em`.
- Datas guardadas como texto ISO `AAAA-MM-DD`, exibidas como `DD/MM/AAAA`.
- `PRAGMA foreign_keys = ON` dentro da função de conexão `get_db_connection()`.
- Validação no Python: tipo do lançamento = tipo da categoria.
- Categorias: `UNIQUE (nome, tipo)`, nova rota de exclusão, bloqueada para categorias em uso (`ON DELETE RESTRICT`).
- "Configurações básicas" retirado do escopo do MVP.
- Dashboard com período padrão = mês atual.
- `/lancamentos/excluir/<id>` deixa de ser listado como página (é só uma ação POST).
- Estrutura de pastas: inclusão de `docs/` e `.gitignore`.

### v1.0

- Versão original em PDF.
