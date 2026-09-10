# overleaf-toolkit

Deploy self-hosted do **Overleaf** via [Overleaf Toolkit](https://docs.overleaf.com/on-premises/getting-started/what-is-the-overleaf-toolkit).

O Toolkit é o método de deploy on-premises recomendado pela própria Overleaf para
Community Edition (CE) e Server Pro. Ele é essencialmente um wrapper em volta do
`docker compose`: `bin/docker-compose` carrega os arquivos de config antes de
chamar o compose real, e a pasta `bin/` traz os utilitários do dia a dia.

## Estrutura

```
.
├── dev            # ponto de entrada único — use este
├── bootstrap.sh   # clona o Toolkit upstream e liga a config deste repo nele
├── config/        # SUA configuração (overleaf.rc, variables.env, version)
├── docs/          # notas de operação
└── toolkit/       # clone do overleaf/toolkit (gitignored, upstream)
```

A ideia: o código do Toolkit fica upstream e atualizável com `git pull`;
só a **sua** configuração é versionada aqui.

## Quick start

```bash
./dev
```

Só isso. O `./dev` faz o bootstrap sozinho na primeira execução (clona o Toolkit,
gera a config, liga o symlink) e sobe os containers. Nas próximas vezes ele só sobe.

Depois abra `http://localhost/launchpad` para criar a conta admin.

## Comandos

| Comando | Para quê |
|---|---|
| `./dev` | sobe o Overleaf (attached) |
| `./dev up -d` | sobe em background |
| `./dev stop` / `./dev restart` | para / reinicia |
| `./dev status` | o que está rodando |
| `./dev logs` | segue os logs |
| `./dev shell` / `./dev mongo` | shell no container / no MongoDB |
| `./dev doctor` | diagnóstico do deploy |
| `./dev upgrade` | atualizar a versão do Overleaf |
| `./dev texlive-full` | instala TeX Live completo **e persiste na imagem** |

`./dev help` lista tudo. Os scripts originais do Toolkit continuam em
`toolkit/bin/` se você precisar de algo que o `./dev` não cobre.

## Antes de subir em produção, leia

- [docs/texlive-full.md](docs/texlive-full.md) — **a imagem oficial vem com TeX Live
  mínimo.** Sem isso, metade dos seus `\usepackage` quebra. O `./dev texlive-full`
  automatiza a correção, mas leia para entender o que ele faz.
- [docs/community-edition-plus.md](docs/community-edition-plus.md) — o que a CE
  *não* tem em relação ao overleaf.com, e o fork da comunidade que reimplementa
  parte disso.

## Segurança

Este repo é privado por um motivo: `config/variables.env` acaba carregando URL do
site, e-mail do admin e, dependendo do setup, credenciais de SMTP e LDAP.
Se for abrir para mais gente, mova os segredos para
[SOPS](https://github.com/getsops/sops) ou git-crypt antes.

`data/` (projetos dos usuários, Mongo, Redis) está no `.gitignore` e nunca deve
ser commitado.
