# CE vs. Server Pro, e o fork da comunidade

## O que a Community Edition não tem

A CE é gratuita e self-hosted, mas várias features que você conhece do
overleaf.com são exclusivas do **Server Pro** (pago):

- SSO via **LDAP** e **SAML**
- **Track changes** (controle de alterações)
- **Sandboxed Compiles** (compilação isolada por usuário)
- **Git Bridge**

Referência: [Server Pro vs. Community Edition](https://docs.overleaf.com/on-premises/welcome/server-pro-vs.-community-edition).

## overleaf-cep — "Community Edition Plus"

Existe um fork mantido pela comunidade que reimplementa parte dessas features em
cima da CE:

**https://github.com/yu-i-i/overleaf-cep**

Ele se descreve como "CE extended with free premium features" e traz coisas como
track changes e autenticação LDAP/SAML.

### Duas ressalvas antes de sair usando

1. **Sem Sandboxed Compiles.** O próprio projeto avisa: a CE estendida é para
   ambientes onde **todos os usuários são confiáveis**. Sem sandbox, LaTeX é
   execução de código arbitrário — `\write18`, leitura de arquivos do container.
   Não coloque isso aberto na internet com cadastro livre.

2. **Não é a imagem oficial.** O repo traz os próprios Dockerfiles (uma imagem
   base com dependências + texlive, e a imagem `sharelatex/sharelatex` por cima).
   Você passa a fazer build local e a depender de um mantenedor terceiro para
   patches de segurança — o `bin/upgrade` do Toolkit não vai te salvar.

Se o objetivo é uso institucional com usuários externos, o caminho suportado é
Server Pro. Se é um time interno pequeno e confiável, o fork é uma opção real.

## Não confundir com o TeX Live

Deixar o Overleaf "parecido com o overleaf.com" tem **dois eixos independentes**:

| Sintoma | Causa | Solução |
|---|---|---|
| `\usepackage` falha, compilação quebra | TeX Live mínimo na imagem | [docs/texlive-full.md](texlive-full.md) |
| Falta track changes, LDAP, SSO | features de Server Pro | pagar Server Pro, ou `overleaf-cep` |

A maioria das reclamações de "o self-hosted é limitado" é na verdade o primeiro
caso, que se resolve com `tlmgr install scheme-full`.
