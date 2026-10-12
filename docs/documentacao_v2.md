# Sistema Financeiro da Casa — Versão 2

Documentação funcional e técnica da segunda versão.

> **Versão 2.0 (planejamento)** — 11/10/2026.
> Parte do MVP concluído (etapas 1 a 8, ver [documentacao_mvp.md](documentacao_mvp.md)).
> Este documento define **o que** será construído e **as regras**, antes de qualquer código.

---

## 1. Objetivo da Versão 2

O MVP registra receitas e despesas. A Versão 2 faz o sistema refletir **como o dinheiro realmente se movimenta numa casa**:

- **Formas de pagamento**: dinheiro, Pix, débito, crédito...
- **Cartões de crédito**, com faturas e **compras parceladas**.
- **Despesas recorrentes**: aluguel, internet e assinaturas, cadastradas uma vez só.
- **Orçamento mensal por categoria**: quanto se pretende gastar × quanto foi gasto.
- **Gráficos** no dashboard e **exportação** para Excel/CSV.

### Decisões já tomadas

| Decisão | Escolha | Consequência |
|---|---|---|
| Em que mês conta uma compra no crédito? | **No mês da fatura** | O saldo do dashboard mostra o dinheiro que realmente sai no mês |
| Compras parceladas? | **Sim** | Cada parcela vira um lançamento na sua fatura |

## 2. Escopo

```
Versão 2
├── Migrações do banco (alterar tabelas sem perder dados) + backup
├── Forma de pagamento nos lançamentos
├── Cartões de crédito
│   ├── Cadastro de cartões (nome, fechamento, vencimento, limite)
│   ├── Compras no crédito (à vista e parceladas)
│   └── Faturas por mês
├── Despesas recorrentes
├── Orçamento mensal por categoria
├── Gráficos no dashboard
└── Exportar lançamentos (CSV para Excel)
```

### Fora da Versão 2

- Contas bancárias e saldo por conta (o saldo continua sendo receitas − despesas).
- Pagamento de fatura, juros, rotativo, estornos e cashback.
- Cartão de débito como "cartão" cadastrado (débito é só uma forma de pagamento).
- Login, múltiplos usuários, deploy (Versão 3).

---

## 3. Migrações do banco de dados

### O problema
Até o MVP, mudar o banco era fácil: o banco estava vazio. Agora ele tem **dados reais**, e não pode ser apagado e recriado.

### A solução: migrações numeradas
Cada mudança no banco vira um arquivo SQL numerado, que roda **uma única vez**:

```
database/
├── schema.sql                     (estrutura do MVP — continua igual)
└── migracoes/
    ├── 001_forma_pagamento.sql
    ├── 002_cartoes.sql
    ├── 003_compras_cartao.sql
    ├── 004_recorrencias.sql
    └── 005_orcamentos.sql
```

O SQLite tem um número guardado dentro do próprio arquivo do banco, o **`PRAGMA user_version`** (começa em 0). A função `init_db()`:

1. roda o `schema.sql` (como hoje — idempotente);
2. lê o `user_version` atual;
3. roda, em ordem, só as migrações com número **maior** que ele;
4. depois de cada uma, atualiza o `user_version`.

Assim, rodar `python db.py` várias vezes continua seguro (idempotente).

### Backup antes de migrar
Antes de aplicar qualquer migração, o `db.py` copia o banco para `backups/database_AAAA-MM-DD_HHMMSS.db`.
A pasta `backups/` fica no `.gitignore` (são dados pessoais).

---

## 4. Forma de pagamento

Novo campo no lançamento: **`forma_pagamento`**.

| Valor no banco | Na tela |
|---|---|
| `pix` | Pix |
| `debito` | Débito |
| `credito` | Crédito |
| `dinheiro` | Dinheiro |
| `boleto` | Boleto |
| `transferencia` | Transferência |

**Regras**
- Obrigatório. Os lançamentos que já existem recebem `pix` na migração (podem ser editados depois).
- Vale para receitas também (ex.: salário por `transferencia`).
- `credito` só pode ser usado em **despesas** e exige um **cartão** (seção 5).
- A lista de lançamentos ganha o filtro "Forma de pagamento".

---

## 5. Cartões de crédito

### 5.1 Cadastro de cartões

| Campo | Exemplo | Regra |
|---|---|---|
| Nome | "Nubank", "Itaú Visa" | Obrigatório |
| Titular | "Érica", "Heberton" | Obrigatório — quem da casa é dono do cartão. Nome + titular é único (cada um pode ter um "Nubank") |
| Dia de fechamento | 3 | Entre 1 e 28 |
| Dia de vencimento | 10 | Entre 1 e 28 |
| Limite | R$ 5.000,00 | Opcional, em centavos |
| Ativo | sim/não | Cartão inativo não aparece para novas compras |

> Por que só até o dia 28? Porque todo mês tem dia 28. Evita a pergunta "qual é o dia 31 de fevereiro?".

Um cartão **com compras não pode ser excluído** — só **inativado** (mesma lógica das categorias).

### 5.2 Em qual fatura cai uma compra?

Cada fatura é identificada pelo **mês do vencimento** (ex.: "fatura de novembro/2026" vence em novembro).

**Regra do fechamento:**
- Compra feita **antes** do dia de fechamento → entra na fatura que fecha naquele mês.
- Compra feita **no dia do fechamento ou depois** → vai para a fatura seguinte.

**Exemplo** — cartão com fechamento dia 3 e vencimento dia 10:

| Data da compra | Fecha em | Fatura (vencimento) |
|---|---|---|
| 02/10/2026 | 03/10/2026 | 10/10/2026 |
| 03/10/2026 | 03/11/2026 | 10/11/2026 |
| 25/10/2026 | 03/11/2026 | 10/11/2026 |

**Quando o vencimento é antes do fechamento no calendário** (ex.: fecha dia 25, vence dia 5): a fatura que vence em 05/11 fecha em 25/10, ou seja, no mês anterior. O cálculo considera isso.

### 5.3 A data do lançamento no crédito

Para que o dashboard conte a compra **no mês da fatura** (decisão da seção 1), cada lançamento no crédito guarda duas datas:

| Campo | Significado | Exemplo |
|---|---|---|
| `data` | Quando o dinheiro sai: o **vencimento da fatura** | 2026-11-10 |
| `data_compra` | Quando a compra foi feita (informativo) | 2026-10-25 |

**Vantagem:** o dashboard, os filtros e os totais **continuam funcionando sem mudanças**, porque todos já usam o campo `data`.
Para as outras formas de pagamento, `data_compra` fica igual a `data`.

### 5.4 Compras parceladas

Uma compra parcelada é registrada uma vez (tabela `compras_cartao`) e gera **uma parcela por fatura** (lançamentos ligados à compra).

**Exemplo** — R$ 1.000,00 em 3x, comprado em 25/10/2026 (fecha dia 3, vence dia 10):

| Parcela | Valor | `data` (fatura) | Descrição na lista |
|---|---|---|---|
| 1/3 | R$ 333,34 | 2026-11-10 | Geladeira (1/3) |
| 2/3 | R$ 333,33 | 2026-12-10 | Geladeira (2/3) |
| 3/3 | R$ 333,33 | 2027-01-10 | Geladeira (3/3) |

**Regras**
- Parcelas: de 1 (à vista) a 24.
- **Divisão em centavos inteiros**: `valor_total // parcelas` para cada uma; a **diferença dos centavos vai na 1ª parcela**. A soma das parcelas é **sempre** igual ao total.
- A parcela *k* cai na fatura da 1ª parcela + (*k* − 1) meses.
- Parcelas são **editadas e excluídas pela compra**, nunca uma por uma: editar a compra recria as parcelas; excluir a compra apaga todas (`ON DELETE CASCADE`).
- Na lista de lançamentos, a parcela mostra "2/3" e o link "Ver compra".

### 5.5 Página de faturas

`/cartoes/<id>/faturas` — para cada mês:

```
Nubank · fecha dia 3, vence dia 10
────────────────────────────────────────────
Fatura de novembro/2026 (vence 10/11)   R$ 1.250,40
  25/10  Geladeira (1/3)       Compras   R$ 333,34
  28/10  Mercado               Aliment.  R$ 917,06
Fatura de dezembro/2026 (vence 10/12)   R$   333,33   ← já comprometido
...
────────────────────────────────────────────
Limite: R$ 5.000,00 · Usado: R$ 1.917,06 · Disponível: R$ 3.082,94
```

- Mostra a fatura atual e as **futuras** (parcelas já comprometidas).
- **Limite usado** = soma das parcelas com vencimento a partir de hoje.

---

## 6. Despesas recorrentes

Contas que se repetem todo mês com o mesmo valor (aluguel, internet, streaming, academia, salário...).

| Campo | Exemplo |
|---|---|
| Descrição | Internet |
| Valor | R$ 120,00 |
| Tipo / Categoria | despesa / Internet |
| Forma de pagamento (e cartão, se crédito) | débito |
| Dia do mês | 15 (1 a 28) |
| Início / Fim | 2026-10 / (vazio = sem fim) |
| Ativa | sim |

### Como os lançamentos são gerados
- No dashboard, um aviso: *"3 contas recorrentes de outubro ainda não foram lançadas — Lançar agora"*.
- O botão cria os lançamentos do mês para todas as recorrências ativas.
- **Sem duplicar:** o lançamento gerado guarda `recorrencia_id` e o mês de referência, com `UNIQUE (recorrencia_id, mes_referencia)`. Gerar duas vezes não cria nada novo (`INSERT OR IGNORE`, como nas categorias iniciais).
- Depois de gerado, é um lançamento comum: pode ser editado (ex.: a conta de luz veio diferente) sem afetar a recorrência.
- Recorrência no crédito: gera uma compra à vista no cartão, no dia indicado (seguindo a regra da fatura).

---

## 7. Orçamento mensal por categoria

Definir **quanto se pretende gastar** em cada categoria de despesa num mês, e comparar com o **realizado**.

| Campo | Exemplo |
|---|---|
| Categoria (só de despesa) | Alimentação |
| Mês | 2026-10 |
| Valor previsto | R$ 1.200,00 |

**Regras**
- Um orçamento por categoria por mês: `UNIQUE (categoria_id, mes)`.
- Botão **"Copiar do mês anterior"**, para não redigitar todo mês.
- O realizado usa o campo `data` (então compras no crédito contam no mês da fatura, coerente com o resto).

**No dashboard**, uma barra por categoria orçada:

| Uso do orçamento | Cor |
|---|---|
| até 80% | azul (normal) |
| de 80% a 100% | amarelo ("atenção") |
| acima de 100% | vermelho ("estourou") |

---

## 8. Gráficos e exportação

### Gráficos (dashboard)
- **Despesas por categoria** do período (rosca/donut).
- **Receitas × despesas dos últimos 6 meses** (barras), para ver a tendência.
- Biblioteca: **Chart.js** (carregada por CDN). É o "JavaScript quando necessário" da documentação do MVP.
- Os dados vão do Python para o JavaScript em JSON (`tojson` do Jinja2).

### Exportar CSV
- Botão **"Exportar"** na lista de lançamentos: baixa um `.csv` **com os filtros aplicados**.
- Formato pensado para o **Excel em português**: separador `;`, valores com vírgula (`250,50`), datas `DD/MM/AAAA`, codificação UTF-8 com BOM (para os acentos abrirem certos).

---

## 9. Banco de dados — novas estruturas

### Migração 001 — forma de pagamento
```sql
ALTER TABLE lancamentos ADD COLUMN forma_pagamento TEXT NOT NULL DEFAULT 'pix'
    CHECK (forma_pagamento IN ('pix', 'debito', 'credito', 'dinheiro', 'boleto', 'transferencia'));
```

### Migração 002 — cartões
```sql
CREATE TABLE cartoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT    NOT NULL,
    titular         TEXT    NOT NULL,
    dia_fechamento  INTEGER NOT NULL CHECK (dia_fechamento BETWEEN 1 AND 28),
    dia_vencimento  INTEGER NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 28),
    limite_centavos INTEGER CHECK (limite_centavos IS NULL OR limite_centavos > 0),
    ativo           INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    UNIQUE (nome, titular)
);
```

### Migração 003 — compras no cartão
```sql
CREATE TABLE compras_cartao (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    cartao_id            INTEGER NOT NULL REFERENCES cartoes(id) ON DELETE RESTRICT,
    descricao            TEXT    NOT NULL,
    valor_total_centavos INTEGER NOT NULL CHECK (valor_total_centavos > 0),
    parcelas             INTEGER NOT NULL CHECK (parcelas BETWEEN 1 AND 24),
    data_compra          TEXT    NOT NULL,   -- AAAA-MM-DD
    categoria_id         INTEGER NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    observacao           TEXT,
    criado_em            TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE lancamentos ADD COLUMN data_compra TEXT;
ALTER TABLE lancamentos ADD COLUMN compra_id INTEGER REFERENCES compras_cartao(id) ON DELETE CASCADE;
ALTER TABLE lancamentos ADD COLUMN parcela_numero INTEGER;
ALTER TABLE lancamentos ADD COLUMN parcela_total INTEGER;
```

### Migração 004 — recorrências
```sql
CREATE TABLE recorrencias (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao       TEXT    NOT NULL,
    valor_centavos  INTEGER NOT NULL CHECK (valor_centavos > 0),
    tipo            TEXT    NOT NULL CHECK (tipo IN ('receita', 'despesa')),
    categoria_id    INTEGER NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    forma_pagamento TEXT    NOT NULL,
    cartao_id       INTEGER REFERENCES cartoes(id) ON DELETE RESTRICT,
    dia_do_mes      INTEGER NOT NULL CHECK (dia_do_mes BETWEEN 1 AND 28),
    mes_inicio      TEXT    NOT NULL,   -- AAAA-MM
    mes_fim         TEXT,               -- AAAA-MM ou NULL (sem fim)
    ativa           INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1))
);

ALTER TABLE lancamentos ADD COLUMN recorrencia_id INTEGER REFERENCES recorrencias(id) ON DELETE SET NULL;
ALTER TABLE lancamentos ADD COLUMN mes_referencia TEXT;   -- AAAA-MM
CREATE UNIQUE INDEX idx_lancamento_recorrencia_mes ON lancamentos (recorrencia_id, mes_referencia);
```

### Migração 005 — orçamentos
```sql
CREATE TABLE orcamentos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id   INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    mes            TEXT    NOT NULL,   -- AAAA-MM
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
    UNIQUE (categoria_id, mes)
);
```

> **Observação técnica:** `ON DELETE SET NULL` (recorrências) significa que, se uma recorrência for excluída, os lançamentos que ela já gerou **continuam existindo**, só perdem a ligação. Já `ON DELETE CASCADE` (compras) significa que excluir uma compra apaga as parcelas dela.

---

## 10. Novas páginas e rotas

| Rota | Página / ação |
|---|---|
| `GET /cartoes` | Lista de cartões |
| `GET, POST /cartoes/novo` | Novo cartão |
| `GET, POST /cartoes/editar/<id>` | Editar / inativar cartão |
| `GET /cartoes/<id>/faturas` | Faturas do cartão |
| `GET, POST /compras/nova` | Nova compra no crédito (à vista ou parcelada) |
| `GET, POST /compras/editar/<id>` | Editar compra (recria as parcelas) |
| `POST /compras/excluir/<id>` | Excluir compra e parcelas |
| `GET /recorrencias` | Lista de recorrências |
| `GET, POST /recorrencias/nova` | Nova recorrência |
| `GET, POST /recorrencias/editar/<id>` | Editar / desativar |
| `POST /recorrencias/gerar` | Gerar os lançamentos do mês |
| `GET, POST /orcamento` | Orçamento do mês (definir valores) |
| `POST /orcamento/copiar` | Copiar do mês anterior |
| `GET /lancamentos/exportar.csv` | Download do CSV |

**Menu:** Dashboard · Lançamentos · Cartões · Orçamento · Mais (Categorias, Recorrências).
**Novo lançamento:** escolhendo "Crédito" como forma de pagamento, o formulário mostra os campos de cartão e parcelas.

---

## 11. Regras de negócio (resumo)

1. Todo lançamento tem forma de pagamento.
2. Crédito só para despesas, e exige um cartão ativo.
3. A fatura de uma compra segue a regra do fechamento (seção 5.2).
4. No crédito, `data` = vencimento da fatura; `data_compra` = dia da compra.
5. A soma das parcelas é exatamente o valor total (diferença na 1ª parcela).
6. Parcelas são editadas/excluídas pela compra.
7. Cartão com compras não pode ser excluído, só inativado.
8. Recorrências geram no máximo um lançamento por mês (sem duplicar).
9. Orçamento: um valor por categoria de despesa por mês.
10. Antes de cada migração, é feito um backup do banco.

---

## 12. Ordem de desenvolvimento

| Etapa | Tema | Conteúdo |
|---|---|---|
| 9 | Migrações | `PRAGMA user_version`, pasta `migracoes/`, backup automático |
| 10 | Forma de pagamento | Migração 001, campo no formulário, filtro e coluna na lista |
| 11 | Cartões | Migração 002, cadastro de cartões |
| 12 | Compras no crédito | Migração 003, cálculo da fatura, parcelas, `compras_cartao` |
| 13 | Faturas | Página de faturas e limite usado |
| 14 | Recorrências | Migração 004, cadastro, geração sem duplicar |
| 15 | Orçamento | Migração 005, definir/copiar, barras no dashboard |
| 16 | Gráficos | Chart.js no dashboard |
| 17 | Exportar | CSV com os filtros aplicados |

## 13. Critério para considerar a Versão 2 concluída

- [ ] Rodar `python db.py` atualiza o banco existente **sem perder dados**, e gera um backup.
- [ ] Registrar um lançamento com forma de pagamento e filtrar por ela.
- [ ] Cadastrar um cartão com fechamento, vencimento e limite.
- [ ] Lançar uma compra à vista no crédito e vê-la no mês da fatura correta.
- [ ] Lançar uma compra parcelada e ver as parcelas nas faturas seguintes, somando o total exato.
- [ ] Excluir uma compra parcelada e todas as parcelas sumirem.
- [ ] Ver as faturas atuais e futuras de um cartão, e o limite disponível.
- [ ] Cadastrar recorrências e gerar os lançamentos do mês sem duplicar.
- [ ] Definir o orçamento do mês e ver previsto × realizado no dashboard.
- [ ] Ver os gráficos no dashboard.
- [ ] Exportar os lançamentos filtrados e abrir no Excel com acentos e valores certos.

## 14. Objetivo de aprendizado

- **Banco de dados:** migrações, `ALTER TABLE`, `PRAGMA user_version`, índices únicos, `ON DELETE CASCADE / SET NULL`.
- **Python:** cálculo com datas (meses seguintes, último dia), divisão inteira e resto (`//` e `%`), módulo `csv`, `shutil` (backup), transações.
- **Flask:** formulários com campos condicionais, respostas de download (`Response`), rotas aninhadas (`/cartoes/<id>/faturas`).
- **JavaScript:** mostrar/esconder campos conforme a escolha; gráficos com Chart.js; JSON.
- **Testes:** como a regra da fatura tem muitos casos, ela ganha **testes automatizados** (`pytest`) — a primeira vez no projeto.

---

## Histórico de revisões

### v2.2 — 12/10/2026
- Situação de cada fatura: **futura** (só parcelas já comprometidas), **aberta** (recebendo as compras de hoje), **fechada** (aguardando vencimento), **vencida**.
- Dashboard: aviso das compras no cartão feitas no período (não entram no saldo) e quadro **"Próximas faturas"** de cada cartão ativo.
- Limite usado = parcelas com vencimento a partir de hoje (aproximação: o sistema não registra o pagamento da fatura).

### v2.1 — 12/10/2026
- Migrações separadas por etapa: 002 só cartões, 003 compras no cartão; recorrências viram 004 e orçamentos 005.
- Cartões ganham **titular** (a casa tem cartões da Érica e do Heberton); unicidade passa a ser nome + titular.
- Forma de pagamento "crédito" fica fora do formulário comum até existirem as compras no cartão (Etapa 12).

### v2.0 — 11/10/2026
- Planejamento inicial da Versão 2.
- Decisões: crédito conta no mês da fatura; com parcelamento.
