# overleaf-toolkit

Deploy self-hosted do **Overleaf** via [Overleaf Toolkit](https://docs.overleaf.com/on-premises/getting-started/what-is-the-overleaf-toolkit).

O Toolkit é o método de deploy on-premises recomendado pela própria Overleaf para
Community Edition (CE) e Server Pro. Ele é essencialmente um wrapper em volta do
`docker compose`: `bin/docker-compose` carrega os arquivos de config antes de
chamar o compose real, e a pasta `bin/` traz os utilitários do dia a dia.

## Estrutura

```
.
├── bootstrap.sh   # clona o Toolkit upstream e liga a config deste repo nele
├── config/        # SUA configuração (overleaf.rc, variables.env, version)
├── docs/          # notas de operação
└── toolkit/       # clone do overleaf/toolkit (gitignored, upstream)
```

A ideia: o código do Toolkit fica upstream e atualizável com `git pull`;
só a **sua** configuração é versionada aqui.

## Quick start

```bash
./bootstrap.sh
cd toolkit
./bin/up
```

Depois abra `http://localhost/launchpad` para criar a conta admin.

## Comandos do Toolkit

| Comando | Para quê |
|---|---|
| `bin/up` / `bin/start` / `bin/stop` | ciclo de vida dos containers |
| `bin/shell` | shell dentro do container do Overleaf |
| `bin/mongo` | shell do MongoDB |
| `bin/logs` | logs dos serviços |
| `bin/upgrade` | atualizar a versão do Overleaf |
| `bin/backup-config` | backup da configuração |
| `bin/doctor` | diagnóstico do deploy |

## Antes de subir em produção, leia

- [docs/texlive-full.md](docs/texlive-full.md) — **a imagem oficial vem com TeX Live
  mínimo.** Sem isso, metade dos seus `\usepackage` quebra. Leia primeiro.
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
