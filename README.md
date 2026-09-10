# Overleaf (snapshot)

Cópia congelada do Overleaf que estava rodando aqui. Não puxa imagem da Overleaf nem do Docker Hub. Se eles tirarem tudo do ar, isto continua.

## Como abrir

1. Instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/), abra e espere o ícone ficar verde.
2. Rode **um** destes:

```bash
npm start
```

```bash
./dev
```

No Windows, pode dar dois cliques em `start.cmd`.

3. Abra http://localhost/launchpad e crie a conta admin (só na primeira vez).

A primeira subida carrega as imagens do próprio repo — alguns GB, demora. Depois é rápido.

| Comando | Para quê |
|---|---|
| `npm start` / `./dev` | sobe |
| `npm stop` / `./dev stop` | para |
| `npm run logs` / `./dev logs` | logs |

Não precisa atualizar nada. A versão está pinada.

## Uma vez: congelar as imagens neste repo

Isto só precisa rodar na máquina onde o Overleaf **já está de pé**, e só se `vendor/images/` ainda estiver vazio:

```bash
./dev pack
git add vendor/images
git commit
```

Sem esse commit, outro computador não tem as imagens e o `npm start` recusa subir (de propósito: não cai no Docker Hub).

`data/` (artigos, Mongo, Redis) é de cada máquina e não vai no git. O repo leva o programa, não os projetos das pessoas.
