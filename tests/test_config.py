from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src import config


class ConfigTests(unittest.TestCase):
    def test_load_settings_reads_dotenv(self) -> None:
        old_token = os.environ.pop("BOT_TOKEN", None)
        old_loaded = config._DOTENV_LOADED
        cwd = Path.cwd()

        try:
            with tempfile.TemporaryDirectory() as td:
                os.chdir(td)
                Path(".env").write_text("BOT_TOKEN=123456:ABCDEF\nTOP_N=20\n", encoding="utf-8")

                config._DOTENV_LOADED = False
                settings = config.load_settings()

                self.assertEqual(settings.bot_token, "123456:ABCDEF")
                self.assertEqual(settings.top_n, 20)
        finally:
            os.chdir(cwd)
            config._DOTENV_LOADED = old_loaded
            if old_token is not None:
                os.environ["BOT_TOKEN"] = old_token
            else:
                os.environ.pop("BOT_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
