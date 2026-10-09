"""Intenções locais e catálogo fechado de páginas GET do NexoBot."""

from dataclasses import dataclass
import re
import unicodedata

from flask import url_for


@dataclass(frozen=True)
class Destino:
    endpoint: str
    rotulo: str
    padroes: tuple[str, ...]
    orientacao: str


# URLs e rótulos usados pela API e pelo widget vêm desta única lista.
DESTINOS = {
    "dashboard": Destino(
        "cliente.dashboard", "Visão Geral",
        (r"\b(?:dashboard|painel)\b", r"\bvisao geral\b",
         r"\b(?:tela|pagina) inicial(?: do cliente)?\b"),
        "Você pode acompanhar as análises da sua empresa na seção Visão Geral, no menu lateral.",
    ),
    "upload": Destino(
        "cliente.upload", "Enviar Relatórios",
        (r"\buploads?\b",
         r"\b(?:enviar|envio|mandar|anexar|anexos?)\b(?:\s+\w+){0,6}\s+"
         r"(?:arquivos?|planilhas?|relatorios?|compras|vendas)\b",
         r"\b(?:pagina|tela|area|aba|secao) (?:de |dos |de meus )?relatorios\b"),
        "Você pode enviar os arquivos de compras e vendas na seção Enviar Relatórios. "
        "Selecione uma análise disponível e anexe os arquivos correspondentes. "
        "A própria página informa quando não há análise disponível para envio.",
    ),
    "historico": Destino(
        "cliente.historico", "Histórico de Análises",
        (r"\bhistorico\b", r"\b(?:analises|relatorios) (?:anteriores|passad[oa]s|antig[oa]s)\b"),
        "Você pode consultar suas análises anteriores na seção Histórico, no menu lateral.",
    ),
    "guia": Destino(
        "cliente.guia", "Guia",
        (r"\b(?:guia|manual)\b", r"\bbase de conhecimento\b"),
        "O Guia reúne os passos para usar o portal. Você pode acessá-lo pelo menu lateral.",
    ),
    "suporte": Destino(
        "cliente.tickets", "Suporte",
        (r"\b(?:suporte|chamados?|tickets?|atendente|atendimento|humano)\b",
         r"\bfalar com (?:a )?(?:equipe|pessoa)\b"),
        "Você pode falar com a equipe NEXO pela seção Suporte. "
        "Abra a página para consultar seus chamados ou preencher um novo chamado.",
    ),
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).lower()
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", texto)).strip()


def validar_destino(destino) -> str | None:
    return destino if isinstance(destino, str) and destino in DESTINOS else None


def urls_destinos() -> dict:
    """Resolve apenas endpoints conhecidos; nunca utiliza uma URL da mensagem."""
    return {nome: url_for(item.endpoint) for nome, item in DESTINOS.items()}


def identificar_destinos(texto: str) -> list[str]:
    texto = normalizar(texto)
    return [nome for nome, item in DESTINOS.items()
            if any(re.search(padrao, texto) for padrao in item.padroes)]


_COMANDO = re.compile(
    r"\b(?:abra|abre|acesse|acessa)\b|"
    r"\bme (?:leve|leva|levar|direcione|direciona|direcionar|redirecione|redireciona|"
    r"mande|manda|coloque|coloca|ponha)\b|"
    r"\b(?:pode|poderia|consegue|conseguiria) (?:me |voce |vc )?"
    r"(?:abrir|acessar|direcionar|redirecionar|levar|mandar|ir|entrar)\b|"
    r"\b(?:quero|queria|gostaria|preciso|desejo) (?:de )?"
    r"(?:ir|acessar|abrir|entrar|ver|consultar|voltar|navegar)\b|"
    r"\b(?:vai|va) (?:para|pra|pro|a|ao|ate)\b|"
    r"^(?:abrir|acessar|direcionar|redirecionar|ir|entrar)\b"
)
_INFORMATIVA = re.compile(
    r"\b(?:como|onde|aonde|qual|quais|quando|explique|explica|ensine|ensina|duvida)\b|"
    r"\b(?:o que|por que|funciona|funcionam)\b|"
    r"\b(?:existe|tem|ha) (?:uma? |alguma? )?(?:pagina|area|tela|local|lugar|aba|secao)\b"
)
_ADMIN = re.compile(r"\b(?:admin|administracao|administrador[ae]?s?|administrativ[oa])\b")
_URL = re.compile(
    r"\b[a-z][a-z0-9+.-]*\s*:\s*/\s*/|"
    r"\b(?:https?|ftp|sftp|wss?|javascript|vbscript|data|file|mailto|tel)\s*:|//|\bwww\.|"
    r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|br|app|gov|edu)\b|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\blocalhost\b",
    re.IGNORECASE,
)
_OPERACAO = re.compile(
    r"\b(?:exclua|apague|delete|publique|dispare|crie|altere|edite|modifique|"
    r"processe|homologue|execute|envie|mande|anexe|troque|cancele|atualize|cadastre)\b|"
    r"\b(?:quero|preciso|pode|consegue) (?:que voce |que vc |voce |vc )?"
    r"(?:excluir|apagar|deletar|publicar|disparar|criar|alterar|editar|modificar|"
    r"processar|homologar|executar|enviar|mandar|anexar|trocar|cancelar|atualizar|cadastrar)\b"
)

# Contexto só completa um comando elíptico ou anafórico. Substantivos fora
# dessa gramática (ex.: "estoque físico") nunca reutilizam um destino antigo.
_CONTEXTO_PALAVRAS = set(
    "entao agora ja sim por favor obrigado obrigada pode poderia consegue conseguiria "
    "quero queria gostaria preciso desejo de que voce vc me mim leve leva levar "
    "direcione direciona direcionar redirecione redireciona redirecionar mande manda "
    "mandar coloca coloque colocar ponha abre abra abrir acesse acessa acessar "
    "vai va ir entrar entre ver consultar voltar navegar para pra pro ate a ao em "
    "na no o essa esse esta este nessa nesse nesta neste aquela aquele pagina tela local parte aba lugar "
    "secao la ali aqui".split()
)
_PREFIXO_DESTINO = set(
    "para pra pro ate a ao o os as na no em de da do das dos meu minha meus minhas "
    "um uma pagina tela local lugar parte aba secao area inicial principal cliente "
    "clientes portal nexo sistema novo nova disponivel abrir ver consultar acessar "
    "falar com equipe onde eu posso pode por favor agora ja so somente logo "
    "rapidinho direto diretamente".split()
)


def _destinos_do_comando(texto: str) -> list[str]:
    # A menção anterior ao verbo ("estou no upload, abra o histórico") não é
    # o destino solicitado. Orações explicativas também não escolhem a rota.
    texto = re.split(r"\b(?:porque|pois|lembra|lembrando|sobre|em vez de|em vez do|estou|estava)\b", texto, maxsplit=1)[0]
    encontrados = [
        (match.start(), nome)
        for nome, item in DESTINOS.items()
        for padrao in item.padroes
        if (match := re.search(padrao, texto))
    ]
    if not encontrados:
        return []
    primeiro = min(posicao for posicao, _ in encontrados)
    if not set(texto[:primeiro].split()) <= _PREFIXO_DESTINO:
        return []
    return list(dict.fromkeys(nome for _, nome in encontrados))


@dataclass(frozen=True)
class Intencao:
    tipo: str
    destino: str | None = None
    resposta: str | None = None


def analisar_navegacao(mensagem: str, ultimo_destino=None) -> Intencao:
    """Classifica localmente antes de consultar qualquer modelo de linguagem."""
    texto = normalizar(mensagem)
    comando = _COMANDO.search(texto)
    informativa = _INFORMATIVA.search(texto)
    direta = bool(comando and (not informativa or comando.start() < informativa.start()))
    if comando and re.search(r"\b(?:ver|consultar)$", comando.group()) and re.match(
        r"\s+(?:como|onde|aonde|qual|quais|o que|por que)\b", texto[comando.end():]
    ):
        direta = False

    if _URL.search(mensagem):
        return Intencao("bloqueada", resposta="O NexoBot só pode abrir páginas permitidas dentro do portal NEXO.")
    if _ADMIN.search(texto):
        return Intencao("bloqueada", resposta="O NexoBot atende as páginas do cliente e não permite acesso à área administrativa.")
    if direta and re.search(r"\b(?:nao|nunca|jamais|nem)\b", texto):
        return Intencao("negada", resposta="Tudo bem. Vou manter você na página atual.")
    # "Me mande para o upload" é navegação; "Envie a planilha" é uma operação.
    for operacao in _OPERACAO.finditer(texto):
        if informativa and informativa.start() < operacao.start():
            continue
        so_mandar_pagina = (
            texto[:operacao.start()].endswith("me ")
            and re.match(r"(?:mande|manda) (?:para|pra|pro|ate)\b", texto[operacao.start():])
        )
        if not so_mandar_pagina:
            return Intencao(
                "operacao", resposta="O NexoBot pode orientar e abrir páginas, mas não executa envios, "
                "exclusões ou alterações por você. Realize a operação na interface apropriada do portal.",
            )

    destinos = (_destinos_do_comando(texto[comando.end():]) if direta
                else identificar_destinos(mensagem))
    if len(destinos) > 1:
        nomes = " ou ".join(DESTINOS[nome].rotulo for nome in destinos)
        return Intencao("esclarecer", resposta=f"Você deseja abrir {nomes}? Escolha uma página.")
    if destinos:
        return Intencao("navegar" if direta else "informar", destino=destinos[0])
    if direta:
        contextual = set(texto.split()) <= _CONTEXTO_PALAVRAS
        destino = validar_destino(ultimo_destino) if contextual else None
        if destino:
            return Intencao("navegar", destino=destino)
        if not contextual:
            return Intencao(
                "esclarecer", resposta="Não identifiquei essa página entre os destinos disponíveis. "
                "Posso abrir Visão Geral, Enviar Relatórios, Histórico, Guia ou Suporte. Qual você deseja?",
            )
        return Intencao("esclarecer", resposta="Qual página você deseja abrir: Visão Geral, Enviar Relatórios, Histórico, Guia ou Suporte?")
    return Intencao("informar")


def acao_navegacao(tipo: str, destino: str) -> dict:
    """Monta a ação somente a partir de um identificador da lista permitida."""
    destino = validar_destino(destino)
    if destino is None or tipo not in {"navegar", "sugerir_navegacao"}:
        return {"acao": None, "destino": None}
    item = DESTINOS[destino]
    acao = {"acao": tipo, "destino": destino, "url": url_for(item.endpoint)}
    if tipo == "sugerir_navegacao":
        acao["rotulo_botao"] = f"Ir para {item.rotulo}"
    return acao
