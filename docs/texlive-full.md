# TeX Live completo na Community Edition

## O problema

A imagem Docker oficial do Overleaf **vem com uma instalação mínima do TeX Live**,
de propósito, para economizar banda no pull. Na prática isso significa que um
documento comum de artigo já falha ao compilar por falta de pacote.

Isso é o "default bem simples" da imagem — não é bug, é escolha de tamanho.

## A correção

Entre no container e instale o esquema completo:

```bash
cd toolkit
./bin/shell
```

Dentro do container:

```bash
tlmgr --version          # confere qual release do TeX Live você tem
tlmgr install scheme-full
tlmgr path add
```

> **`tlmgr path add` é obrigatório.** A partir do release `3.3.0` do Overleaf,
> ele precisa ser rodado depois de **todo** `tlmgr install`, senão os binários
> novos não são symlinkados no PATH do sistema.

Para instalar só o que falta, em vez do esquema inteiro:

```bash
tlmgr install tikzlings tikzmarmots tikzducks
```

## Tornando persistente (o passo que todo mundo esquece)

As mudanças acima estão **no container, não na imagem**. Elas são efêmeras: somem
na primeira vez que o Compose recriar o container — inclusive numa simples
mudança de config.

Saia do shell e faça commit do container numa imagem nova:

```bash
docker commit sharelatex sharelatex/sharelatex:5.0.3-with-texlive-full
echo 5.0.3-with-texlive-full > config/version
./bin/up
```

Ajuste `5.0.3` para a versão que você está rodando (veja `config/version`).

**Isso precisa ser refeito a cada upgrade do Overleaf**, porque o upgrade troca a
imagem base e você perde a camada com o TeX Live completo.

## Server Pro faz diferente

No Server Pro existe **Sandboxed Compiles**, que baixa uma imagem de TeX Live
completa automaticamente e isola a compilação por usuário. Todo o procedimento
acima é específico da Community Edition.

## Fontes

- [Upgrading TeX Live — Overleaf docs](https://docs.overleaf.com/on-premises/installation/upgrading-tex-live)
- [Extending TeX Live — Overleaf docs](https://docs.overleaf.com/on-premises/maintenance/extending-tex-live)
- [toolkit/doc/ce-upgrading-texlive.md](https://github.com/overleaf/toolkit/blob/master/doc/ce-upgrading-texlive.md)
