# Sistema Financeiro da Casa — Versão 3

Login, segurança e publicação na internet.

> **Versão 3.0 (planejamento)** — 12/10/2026.
> Parte da Versão 2 concluída (etapas 9 a 17, ver [documentacao_v2.md](documentacao_v2.md)).
> Este documento define **o que** será construído e **as regras**, antes de qualquer código.

---

## 1. Objetivo

Até a Versão 2, o app roda **só no computador**, e qualquer pessoa que abre o navegador nele tem acesso a tudo. A Versão 3 permite usar o app **de qualquer lugar** (celular, trabalho), com segurança:

- **Login**: só a Érica e o Heberton entram, cada um com a sua senha.
- **Proteções obrigatórias** para um site com dados financeiros na internet.
- **Publicação** no PythonAnywhere, com os dados atuais levados junto.
- **Backup** do banco que fica na internet.

### Decisões já tomadas

| Decisão | Escolha | Consequência |
|---|---|---|
| Banco de dados | **Continua SQLite** | Nenhuma consulta muda; o PythonAnywhere guarda o arquivo do banco |
| Usuários | **Érica e Heberton, acesso total** | Duas contas; os dois veem e editam tudo; sem níveis de permissão |
| Autoria dos lançamentos | **Não registrar** | O login só protege o acesso; os lançamentos não ganham "dono" |
| Hospedagem | **PythonAnywhere** | Feito para Flask, mantém o arquivo SQLite, tem plano gratuito |

> **Por que não Vercel, Render ou similares (no plano grátis)?** Eles apagam os arquivos do servidor a cada reinício ou novo deploy — o `database.db` sumiria junto com todos os dados.

## 2. Escopo

```
Versão 3
├── Configuração segura (.env, SECRET_KEY, debug desligado em produção)
├── Usuários e login
│   ├── Tabela de usuários com senha protegida (hash)
│   ├── Entrar / sair
│   ├── Todas as páginas exigem login
│   ├── Trocar a própria senha
│   └── Criar usuários pelo terminal (não existe página de cadastro)
├── Proteções
│   ├── CSRF em todos os formulários
│   └── Bloqueio após várias senhas erradas
├── Publicação no PythonAnywhere
└── Backup do banco online
```

### Fora da Versão 3
- PostgreSQL (fica para quando houver necessidade real).
- Permissões diferentes por usuário; registro de quem lançou o quê.
- "Esqueci minha senha" por e-mail (com 2 usuários, um pode redefinir a senha do outro pelo terminal).
- Domínio próprio (o endereço será `usuario.pythonanywhere.com`).
- App de celular (o site funciona no navegador do celular).

---

## 3. Configuração segura

### 3.1 O arquivo `.env`
Informações secretas **nunca** vão para o código (o repositório é público). Ficam num arquivo `.env`, que já está no `.gitignore`:

```
SECRET_KEY=uma-sequencia-longa-e-aleatoria
FLASK_DEBUG=0
```

- O pacote **`python-dotenv`** lê esse arquivo e coloca os valores em variáveis de ambiente.
- Um arquivo **`.env.exemplo`** (esse sim no Git) mostra quais variáveis existem, sem os valores reais.

### 3.2 A `SECRET_KEY`
O Flask usa essa chave para **assinar o cookie de sessão** — é o que impede alguém de forjar um cookie dizendo "estou logado como Érica".
- Gerada com `python -c "import secrets; print(secrets.token_hex(32))"`.
- Uma no computador e **outra diferente** no servidor.
- Sem `SECRET_KEY` definida, o app **não inicia** (falha em vez de rodar inseguro).

### 3.3 Modo debug só no computador
O `debug=True` mostra uma página com um **console Python** quando dá erro. No computador é ótimo; na internet seria uma porta aberta: qualquer pessoa poderia executar código no servidor.
- `FLASK_DEBUG=1` só no `.env` do computador.
- No servidor o app roda pelo PythonAnywhere, sem `app.run(debug=True)`.

---

## 4. Usuários e login

### 4.1 Senhas nunca são guardadas
O banco guarda só o **hash** da senha — uma "impressão digital" de mão única:

```
senha digitada:  minhaSenha123
guardado:        scrypt:32768:8:1$Xk2...$9f3a...   (não dá para voltar à senha)
```

No login, o sistema calcula o hash do que foi digitado e compara. Funções do próprio Flask (Werkzeug): `generate_password_hash` e `check_password_hash`.
Se alguém copiar o banco, **não descobre as senhas**.

### 4.2 Tabela `usuarios` (migração 006)

```sql
CREATE TABLE usuarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT    NOT NULL,              -- "Érica", "Heberton" (aparece no menu)
    login           TEXT    NOT NULL UNIQUE,       -- "erica", "heberton" (minúsculo, sem espaço)
    senha_hash      TEXT    NOT NULL,
    tentativas_erradas INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate   TEXT,                          -- data/hora até quando o login está bloqueado
    criado_em       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 4.3 Criar usuários pelo terminal
Não existe página "cadastre-se" — seria um convite para estranhos. Usuários são criados por um **comando do Flask**:

```bash
flask --app app criar-usuario
# Nome: Érica
# Login: erica
# Senha: ******** (não aparece na tela)
# Confirme a senha: ********
```

O mesmo comando com um login existente **redefine a senha** (é o "esqueci minha senha" desta versão).

### 4.4 Regras do login
- Senha com **pelo menos 10 caracteres**.
- **Todas** as páginas exigem login, exceto a própria tela de login e os arquivos de estilo (`/static`).
- Quem tenta abrir uma página sem estar logado vai para o login e, depois de entrar, **volta para a página que queria**.
- Mensagem de erro **sempre igual**: *"Login ou senha incorretos."* — não revela se o login existe.
- **5 senhas erradas seguidas** → login bloqueado por **15 minutos**. Acertar a senha zera o contador.
- A sessão dura **30 dias** se marcar "Manter conectado"; senão, até fechar o navegador.
- **Sair** encerra a sessão (botão no menu, via POST).
- **Trocar senha**: página própria, pedindo a senha atual.

### 4.5 Sessão
O Flask guarda na sessão (cookie assinado com a `SECRET_KEY`) só o `id` do usuário. O cookie é configurado como:
- `HttpOnly` — o JavaScript da página não consegue ler;
- `Secure` — só viaja por HTTPS (no servidor);
- `SameSite=Lax` — não é enviado em formulários vindos de outros sites.

---

## 5. Proteção contra CSRF

**O ataque:** com a Érica logada, um site malicioso que ela visite poderia conter um formulário invisível que envia um POST para `/lancamentos/excluir/1` do nosso app — e o navegador mandaria junto o cookie de login.

**A defesa:** todo formulário POST leva um **token secreto** gerado pelo servidor; um site de fora não tem como saber esse valor, então o POST dele é recusado.
- Pacote **Flask-WTF** (`CSRFProtect`): protege todas as rotas POST de uma vez.
- Em **cada** `<form method="post">` entra uma linha: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- Um teste automatizado confere que nenhum formulário ficou sem o token.

---

## 6. Publicação no PythonAnywhere

### 6.1 Como fica
```
Navegador (celular/PC) ──HTTPS──▶ usuario.pythonanywhere.com
                                     │
                                     ├── código: clonado do GitHub (git pull para atualizar)
                                     ├── venv + requirements.txt
                                     ├── .env com a SECRET_KEY de produção
                                     └── database.db  (os dados de vocês, enviado uma vez)
```

### 6.2 Passo a passo (resumo — o detalhado vai no README)
1. Criar conta no PythonAnywhere.
2. Num console Bash de lá: `git clone` do repositório, criar o venv, `pip install -r requirements.txt`.
3. Criar o `.env` de produção (nova `SECRET_KEY`, `FLASK_DEBUG=0`).
4. Enviar o `database.db` atual pela aba **Files** (os dados continuam os mesmos) e rodar `python db.py` para aplicar as migrações novas.
5. Criar os usuários com `flask --app app criar-usuario`.
6. Na aba **Web**: novo app Flask "manual", apontar o arquivo WSGI e o venv, marcar **Force HTTPS**, configurar `/static`.
7. Recarregar e testar pelo celular.

### 6.3 Atualizar depois
Mudou o código no computador → `git push` → no PythonAnywhere: `git pull`, `python db.py` (se houver migração) e **Reload** na aba Web.

### 6.4 Uso no dia a dia: um banco só
Depois de publicado, **o banco "oficial" é o do servidor**. O banco do computador vira só de testes — senão os lançamentos ficariam divididos entre os dois.

### 6.5 Limitações do plano gratuito
- Endereço `usuario.pythonanywhere.com`.
- É preciso entrar no painel periodicamente para manter o app ativo (o PythonAnywhere avisa por e-mail).
- Recursos de processamento limitados — suficiente para 2 pessoas.

---

## 7. Backup do banco online

Com o banco na internet, o backup automático do `db.py` acontece **no servidor**, a cada migração. Além disso:
- **Baixar backup**: página no app que gera uma cópia do banco para download (só para quem está logado).
- Rotina sugerida: baixar uma cópia **toda semana** e guardar no computador ou no Google Drive.
- O `.gitignore` continua garantindo que o banco nunca vai para o GitHub.

---

## 8. Novas rotas

| Rota | Página / ação |
|---|---|
| `GET, POST /login` | Entrar |
| `POST /logout` | Sair |
| `GET, POST /conta/senha` | Trocar a própria senha |
| `GET /conta/backup` | Baixar uma cópia do banco |
| comando `flask criar-usuario` | Criar usuário / redefinir senha (terminal) |

O menu ganha, à direita: **nome de quem está logado · Trocar senha · Sair**.

---

## 9. Regras de segurança (resumo)

1. Nenhum segredo no código: `SECRET_KEY` no `.env`.
2. Senhas só como hash; mínimo de 10 caracteres.
3. Todas as páginas exigem login (exceto login e `/static`).
4. Todo formulário POST tem token CSRF.
5. 5 tentativas erradas → bloqueio de 15 minutos; mensagem de erro não revela se o login existe.
6. Debug nunca ligado no servidor.
7. HTTPS obrigatório no servidor; cookie de sessão `Secure`, `HttpOnly`, `SameSite=Lax`.
8. Sem página de cadastro: usuários só pelo terminal.

---

## 10. Ordem de desenvolvimento

| Etapa | Tema | Conteúdo |
|---|---|---|
| 18 | Configuração | `.env`, `python-dotenv`, `SECRET_KEY` obrigatória, debug pelo `.env` |
| 19 | Usuários e login | Migração 006, comando `criar-usuario`, login/logout, todas as rotas protegidas |
| 20 | Proteções | CSRF em todos os formulários, bloqueio por tentativas, trocar senha, cookie seguro |
| 21 | Preparar a publicação | Arquivo WSGI, `README.md` completo (com o passo a passo), baixar backup |
| 22 | Publicar | Deploy no PythonAnywhere junto com você, migrar os dados, testar no celular |

## 11. Critério para considerar a Versão 3 concluída

- [ ] Sem login, nenhuma página do app abre (vai para a tela de login).
- [ ] Érica e Heberton entram, cada um com a sua senha.
- [ ] 5 senhas erradas bloqueiam o login por 15 minutos.
- [ ] Um formulário enviado sem token CSRF é recusado.
- [ ] É possível trocar a própria senha.
- [ ] A `SECRET_KEY` não aparece em nenhum arquivo do GitHub.
- [ ] O app está no ar em `usuario.pythonanywhere.com`, com HTTPS, e abre no celular.
- [ ] Os dados que estavam no computador estão no servidor.
- [ ] É possível baixar um backup do banco.

## 12. Objetivo de aprendizado

- **Segurança web:** hash de senha, sessão e cookies, CSRF, força bruta, por que o debug é perigoso.
- **Flask:** `before_request`, `session`, `flash`, comandos de terminal (`@app.cli.command`), configuração por ambiente.
- **Python:** variáveis de ambiente, `secrets`, `getpass`.
- **Deploy:** servidor WSGI, ambiente de produção × desenvolvimento, atualizar um app no ar.

---

## Histórico de revisões

### v3.0 — 12/10/2026
- Planejamento inicial da Versão 3.
- Decisões: manter SQLite; Érica e Heberton com acesso total; sem registro de autoria; hospedagem no PythonAnywhere.
