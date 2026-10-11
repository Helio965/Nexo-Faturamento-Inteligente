"""Helpers HTTP que exercitam autenticação e CSRF reais da aplicação.

As requests devem ocorrer fora de um app_context mantido entre clientes.
Nenhum helper injeta valores internos da sessão ou presume login bem-sucedido.
"""

from html.parser import HTMLParser

from .factories import TEST_PASSWORD


class _CsrfParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.token = None

    def handle_starttag(self, tag, atributos):
        attrs = dict(atributos)
        if tag == "meta" and attrs.get("name") == "csrf-token":
            self.token = attrs.get("content")
        elif tag == "input" and attrs.get("name") == "csrf_token" and not self.token:
            self.token = attrs.get("value")


def csrf_token(client, path="/auth/login"):
    """Obtém o token do HTML real, seguindo redirects locais do Flask client."""
    resposta = client.get(path, follow_redirects=True)
    if resposta.status_code != 200:
        raise RuntimeError(f"Página CSRF retornou HTTP {resposta.status_code}.")
    parser = _CsrfParser()
    parser.feed(resposta.get_data(as_text=True))
    if not parser.token:
        raise RuntimeError("Template não forneceu token CSRF.")
    return parser.token


def login(client, email, senha=TEST_PASSWORD, **kwargs):
    """Faz GET/POST reais; retorna a resposta para inspeção, inclusive recusas.

    kwargs são repassados ao POST do test client. data pode substituir campos
    para cenários negativos; path permite parâmetros na URL de login.
    """
    path = kwargs.pop("path", "/auth/login")
    token = csrf_token(client, path)
    dados = {"email": email, "senha": senha, "csrf_token": token}
    dados.update(kwargs.pop("data", {}) or {})
    return client.post(path, data=dados, **kwargs)


def logout(client, **kwargs):
    """Usa a rota GET atualmente implementada, sem modificar a sessão à mão."""
    return client.get("/auth/logout", **kwargs)
