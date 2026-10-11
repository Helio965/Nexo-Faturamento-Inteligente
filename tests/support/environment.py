"""Actual NEXO factory backed by disposable files and mocked external services.

Use ``with TestEnvironment() as env`` or ``env.start(); ...; env.close()``.
Applications may be nested, but their environments must close in reverse order:
the production extensions and service patches are process-wide objects.
No application context is kept open between HTTP requests.
"""

from contextlib import ExitStack
from datetime import timedelta
import importlib
import os
from pathlib import Path
import secrets
import tempfile
from unittest.mock import patch


def _deny_network(*args, **kwargs):
    raise RuntimeError("Real network access is disabled in isolated NEXO tests.")


def _snapshot_object(instance):
    """Copy mutable extension settings without copying servers or connections."""
    return {
        key: value.copy() if isinstance(value, (dict, list, set)) else value
        for key, value in vars(instance).items()
    }


def _restore_object(instance, state):
    vars(instance).clear()
    vars(instance).update(state)


class TestEnvironment:
    """A fresh SQLite schema, real Flask routes, and lifetime-scoped mocks.

    CSRF is enabled unless explicitly requested otherwise. Public paths become
    available after ``start()`` and remain available for cleanup assertions.
    ``close()`` is idempotent; a closed environment cannot be restarted.
    """

    def __init__(self, *, csrf_enabled=True):
        if not isinstance(csrf_enabled, bool):
            raise TypeError("csrf_enabled must be an explicit boolean")
        self.csrf_enabled = csrf_enabled
        self.app = None
        self.db = None
        self.root = None
        self.database_path = None
        self.uploads_path = None
        self.services = None
        self._stack = None
        self._closed = False
        self._extensions = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def start(self):
        if self._closed:
            raise RuntimeError("This test environment is already closed")
        if self._stack is not None:
            return self
        self._stack = stack = ExitStack()
        try:
            temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix="nexo-tests-"))
            self.root = Path(temporary).resolve()
            self.database_path = self.root / "test.sqlite"
            self.uploads_path = self.root / "uploads"
            database_uri = f"sqlite:///{self.database_path.as_posix()}"
            secret_key = secrets.token_hex(32)
            stack.enter_context(patch.dict(os.environ, {
                "SECRET_KEY": secret_key,
                "DATABASE_URL": database_uri,
                "DIRECT_URL": database_uri,
                "NEXO_DB_DIRECT": "0",
                "FLASK_ENV": "development",
                "UPLOAD_FOLDER": str(self.uploads_path),
                "MAX_CONTENT_LENGTH_MB": "20",
                "ADMIN_EMAIL": "admin@example.test",
                "ADMIN_NOME": "Test administrator",
                "ADMIN_SENHA": "",
                "MAIL_SERVER": "smtp.invalid",
                "MAIL_PORT": "25",
                "MAIL_USE_TLS": "false",
                "MAIL_USE_SSL": "false",
                "MAIL_USERNAME": "",
                "MAIL_PASSWORD": "",
                "MAIL_DEFAULT_SENDER": "nexo@example.test",
                "ANTHROPIC_API_KEY": "",
                "ANTHROPIC_MODEL": "test-only-model",
                "HF_API_TOKEN": "",
                "HF_MODEL": "test-only-model",
                "RATELIMIT_STORAGE_URI": "memory://",
                "SOCKETIO_CORS_ORIGINS": "http://localhost,http://127.0.0.1",
            }))
            # This precedes the first config import, including ProductionConfig's
            # eager SECRET_KEY read. A local .env is never read by the helper.
            stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
            for target in ("socket.socket.connect", "socket.socket.connect_ex",
                           "socket.create_connection", "socket.getaddrinfo"):
                stack.enter_context(patch(target, side_effect=_deny_network))

            app_module = importlib.import_module("app")
            config_module = importlib.import_module("config")
            self._extensions = extensions = importlib.import_module("extensions")
            self.db = extensions.db
            # Register decorator metadata once before capturing mutable state.
            # Their route functions remain the real application's functions.
            for module in ("blueprints.auth", "blueprints.admin", "blueprints.cliente",
                           "blueprints.notificacoes", "blueprints.api", "realtime"):
                importlib.import_module(module)

            for extension in (extensions.socketio, extensions.limiter,
                              extensions.login_manager, extensions.mail,
                              extensions.migrate, extensions.csrf):
                stack.callback(_restore_object, extension, _snapshot_object(extension))

            self._prepare_socketio(extensions.socketio)
            from .services import ExternalServices
            self.services = stack.enter_context(ExternalServices())
            # Register before factory execution, so partial initialization also
            # releases engines and sessions before mocks and settings unwind.
            stack.callback(self._release_runtime)

            configuration = type("IsolatedNexoConfig", (config_module.Config,), {
                "TESTING": True,
                "DEBUG": False,
                "SECRET_KEY": secret_key,
                "SESSION_PERMANENT": False,
                "PERMANENT_SESSION_LIFETIME": timedelta(hours=8),
                "SESSION_COOKIE_HTTPONLY": True,
                "SESSION_COOKIE_SAMESITE": "Lax",
                "SESSION_COOKIE_SECURE": False,
                "WTF_CSRF_ENABLED": self.csrf_enabled,
                "WTF_CSRF_CHECK_DEFAULT": True,
                "WTF_CSRF_TIME_LIMIT": None,
                "RATELIMIT_ENABLED": False,
                "RATELIMIT_STORAGE_URI": "memory://",
                "RATELIMIT_HEADERS_ENABLED": False,
                "SOCKETIO_CORS_ORIGINS": ["http://localhost", "http://127.0.0.1"],
                "SQLALCHEMY_DATABASE_URI": database_uri,
                "SQLALCHEMY_DIRECT_URI": database_uri,
                "SQLALCHEMY_BINDS": {},
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "SQLALCHEMY_ECHO": False,
                "SQLALCHEMY_ENGINE_OPTIONS": {},
                "ADMIN_EMAIL": "admin@example.test",
                "ADMIN_NOME": "Test administrator",
                "ADMIN_SENHA": None,
                "UPLOAD_FOLDER": self.uploads_path,
                "MAX_CONTENT_LENGTH": 20 * 1024 * 1024,
                "MAIL_SERVER": "smtp.invalid",
                "MAIL_PORT": 25,
                "MAIL_USE_TLS": False,
                "MAIL_USE_SSL": False,
                "MAIL_USERNAME": None,
                "MAIL_PASSWORD": None,
                "MAIL_DEFAULT_SENDER": "nexo@example.test",
                "MAIL_DEBUG": False,
                "MAIL_SUPPRESS_SEND": True,
                "MAIL_ATIVO": False,
                "ALLOWED_EXTENSIONS": {"csv", "xlsx"},
                "ANTHROPIC_API_KEY": None,
                "ANTHROPIC_MODEL": "test-only-model",
                "HF_API_TOKEN": None,
                "HF_MODEL": "test-only-model",
                "SERVER_NAME": None,
                "APPLICATION_ROOT": "/",
                "PREFERRED_URL_SCHEME": "http",
            })
            config_name = f"isolated_test_{secrets.token_hex(8)}"
            actual_flask = app_module.Flask

            def temporary_instance(*args, **kwargs):
                kwargs["instance_path"] = str(self.root / "instance")
                self.app = actual_flask(*args, **kwargs)
                return self.app

            with patch.dict(config_module.config_by_name, {config_name: configuration}), \
                    patch.object(app_module, "Flask", temporary_instance):
                self.app = app_module.create_app(config_name)
            with self.app.app_context():
                self._assert_isolated_engines()
                self.db.create_all()
            return self
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _prepare_socketio(socketio):
        # Cached realtime imports must not leave later factories without their
        # handlers. Preserve the shared object's identity and restore it on exit.
        from flask_socketio import SocketIO
        realtime = importlib.import_module("realtime")
        vars(socketio).clear()
        vars(socketio).update(vars(SocketIO(async_mode="threading", logger=False,
                                          engineio_logger=False)))
        socketio.on_event("connect", realtime._on_connect)
        socketio.on_event("disconnect", realtime._on_disconnect)

    def _assert_isolated_engines(self):
        engines = self.db.engines
        if set(engines) != {None}:
            raise RuntimeError("Unexpected database binds in isolated NEXO tests")
        for engine in engines.values():
            database = engine.url.database
            if (engine.url.get_backend_name() != "sqlite" or not database
                    or not Path(database).is_absolute()
                    or Path(database).resolve() != self.database_path):
                raise RuntimeError("Only the temporary SQLite database is allowed in isolated NEXO tests")

    def _release_runtime(self):
        try:
            if self.app is not None and "sqlalchemy" in self.app.extensions:
                with self.app.app_context():
                    try:
                        self.db.session.remove()
                    finally:
                        engines = self.db._app_engines.pop(self.app, {})
                        for engine in engines.values():
                            engine.dispose()
        finally:
            server = self._extensions.socketio.server
            if server is not None:
                server.shutdown()

    def create_client(self):
        if self._stack is None or self._closed or self.app is None:
            raise RuntimeError("Start the test environment before creating clients")
        return self.app.test_client()

    def close(self):
        if self._closed:
            return
        self._closed = True
        stack, self._stack = self._stack, None
        if stack is not None:
            stack.close()
