"""Per-test unittest lifecycle for the shared isolated environment."""

import unittest

from .environment import TestEnvironment


class IsolatedTestCase(unittest.TestCase):
    """Override csrf_enabled=False only when a test deliberately excludes CSRF.

    Use short ``with self.app.app_context():`` blocks for database operations;
    HTTP clients keep their own independent contexts, sessions and CSRF tokens.
    """

    csrf_enabled = True

    def setUp(self):
        super().setUp()
        self.env = TestEnvironment(csrf_enabled=self.csrf_enabled)
        self.addCleanup(self.env.close)
        self.env.start()
        self.app = self.env.app
        self.db = self.env.db
