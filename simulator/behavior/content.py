"""Context-aware text generation using ONLY uinput-safe characters.

To ensure compatibility with kernel-level input (uinput) and avoid
needing shift-modifier complexity, all generated text uses:
  lowercase a-z, digits 0-9, space, newline, and a small set of
  unshifted punctuation: - = [ ] backslash ; ' ` , . /
"""
import random
from simulator.context.windows import WindowType


class ContentGenerator:
    """Produces realistic text bursts matched to the current context."""

    # Safe words that only use a-z and 0-9
    _WORDS = [
        "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
        "function", "return", "data", "vector", "index", "query", "result",
        "build", "test", "deploy", "monitor", "alert", "scale", "check",
        "user", "interface", "component", "state", "props", "render", "view",
        "async", "await", "promise", "callback", "middleware", "router",
        "python", "docker", "git", "status", "pull", "push", "merge",
        "error", "warning", "success", "failed", "passed", "skipped",
        "config", "settings", "options", "default", "custom", "value",
        "import", "export", "module", "package", "library", "version",
        "client", "server", "request", "response", "header", "cookie",
        "database", "table", "column", "record", "query", "select",
        "api", "rest", "json", "xml", "yaml", "csv", "txt",
    ]

    # Safe shell-like commands (only safe chars)
    _SHELL_CMDS = [
        "ls -la\n",
        "git status\n",
        "git log\n",
        "docker ps\n",
        "python3 -m pytest\n",
        "npm run build\n",
        "cd src\n",
        "cat readme.txt\n",
        "make clean\n",
        "sudo apt update\n",
    ]

    # Safe code-like lines (only safe chars)
    _CODE_LINES = [
        "def process(data):\n",
        "    result = []\n",
        "    for item in data:\n",
        "        result.append(item)\n",
        "    return result\n",
        "if __name__ == '__main__':\n",
        "    main()\n",
        "class Vector:\n",
        "    def __init__(self, x, y):\n",
        "        self.x = x\n",
        "        self.y = y\n",
        "# todo refactor into smaller functions\n",
        "import json\n",
        "import os\n",
        "config = json.load(open('config.json'))\n",
    ]

    # Safe search queries
    _SEARCH_QUERIES = [
        "python asyncio best practices",
        "docker compose volume permissions",
        "react useeffect cleanup function",
        "postgres jsonb indexing",
        "rust ownership explained",
        "systemd service restart policy",
    ]

    # Safe prose (only safe chars)
    _PROSE = [
        "the quick brown fox jumps over the lazy dog",
        "please review the attached document and let me know",
        "we should schedule a follow up meeting next week",
        "the deployment pipeline completed successfully",
        "note to self check the error logs before pushing",
    ]

    def generate(self, window_type: WindowType, burst_chars: int = 40) -> str:
        if window_type == WindowType.TERMINAL:
            return random.choice(self._SHELL_CMDS)
        if window_type == WindowType.EDITOR:
            return random.choice(self._CODE_LINES)
        if window_type == WindowType.BROWSER:
            q = random.choice(self._SEARCH_QUERIES)
            return q + "\n"
        # Generic prose
        words = random.choices(self._WORDS, k=random.randint(5, 12))
        return " ".join(words) + ".\n"
