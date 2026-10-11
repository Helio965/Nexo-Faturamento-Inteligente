"""Captura serviços externos sem rede e sem alterar controles do Flask.

SMTP mantém renderização real, com apenas sua thread de envio executada de
forma síncrona. IA/HF indisponíveis por padrão exercitam o fallback existente;
respostas e falhas podem ser configuradas nos argumentos ou nos mocks públicos.
"""

from contextlib import ExitStack
import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


_UNSET = object()


def _restaurar_modulo(nome, original):
    if original is _UNSET:
        sys.modules.pop(nome, None)
    else:
        sys.modules[nome] = original


class _ImmediateThread:
    """Substitui somente emails.threading.Thread; não cria threads reais."""

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None,
                 daemon=None):
        if group is not None:
            raise ValueError("group deve ser None.")
        self.target, self.args, self.kwargs = target, args, kwargs or {}
        self.name, self.daemon, self._started = name, daemon, False

    def start(self):
        if self._started:
            raise RuntimeError("Thread de teste já iniciada.")
        self._started = True
        if self.target is not None:
            self.target(*self.args, **self.kwargs)

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return False


class ExternalServices:
    """Context manager restaurável; mocks ficam ativos apenas em start/close.

    anthropic é o mock do construtor; messages_create captura a chamada do SDK.
    Para mudar o fallback depois de start, configure side_effect=None e
    return_value no mock desejado. smtp/socket podem receber side_effect também.
    """

    def __init__(self, *, anthropic_response=_UNSET, hf_response=_UNSET,
                 anthropic_error=_UNSET, hf_error=_UNSET,
                 mail_error=None, socket_error=None):
        self.mail_send = Mock(name="mail.send", side_effect=mail_error, return_value=None)
        self.socket_emit = Mock(name="socketio.emit", side_effect=socket_error, return_value=None)
        self.messages_create = Mock(name="anthropic.messages.create")
        self.hf_post = Mock(name="httpx.post")
        self.anthropic = Mock(
            name="anthropic.Anthropic",
            return_value=SimpleNamespace(messages=SimpleNamespace(create=self.messages_create)),
        )
        self._configurar(self.messages_create, anthropic_response, anthropic_error, "Anthropic")
        self._configurar(self.hf_post, hf_response, hf_error, "Hugging Face")
        self._stack = None

    @staticmethod
    def _configurar(mock, resposta, erro, nome):
        if erro is not _UNSET:
            mock.side_effect = erro
        elif resposta is _UNSET:
            mock.side_effect = RuntimeError(f"{nome} indisponível no teste isolado.")
        if resposta is not _UNSET:
            mock.return_value = resposta

    def start(self):
        if self._stack is not None:
            return self
        stack = ExitStack()
        try:
            emails = importlib.import_module("emails")
            extensions = importlib.import_module("extensions")
            httpx = importlib.import_module("httpx")
            try:
                anthropic = importlib.import_module("anthropic")
            except ModuleNotFoundError as exc:
                if exc.name != "anthropic":
                    raise
                anthropic = ModuleType("anthropic")
                original = sys.modules.get("anthropic", _UNSET)
                sys.modules["anthropic"] = anthropic
                # Restaura só esta entrada: imports legítimos durante o teste
                # devem continuar no cache de módulos ao encerrar o ambiente.
                stack.callback(_restaurar_modulo, "anthropic", original)
            stack.enter_context(patch.object(emails.mail, "send", self.mail_send))
            stack.enter_context(patch.object(emails, "threading", SimpleNamespace(Thread=_ImmediateThread)))
            stack.enter_context(patch.object(extensions.socketio, "emit", self.socket_emit))
            stack.enter_context(patch.object(anthropic, "Anthropic", self.anthropic, create=True))
            stack.enter_context(patch.object(httpx, "post", self.hf_post))
        except BaseException:
            stack.close()
            raise
        self._stack = stack
        return self

    def close(self):
        if self._stack is not None:
            stack, self._stack = self._stack, None
            stack.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        if self._stack is None:
            return False
        stack, self._stack = self._stack, None
        return stack.__exit__(exc_type, exc_value, traceback)
