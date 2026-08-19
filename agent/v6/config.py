from pathlib import Path

DEFAULT_MODEL = "openai/gpt-5.4-mini"

# Resolves relative to this file's own location so it works both locally
# (repo root as cwd) and on Vercel's Python runtime (whatever cwd it uses).
KB_ROOT = (Path(__file__).resolve().parent.parent.parent / "kb" / "wiki").resolve()
