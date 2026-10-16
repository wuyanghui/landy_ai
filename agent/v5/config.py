DEFAULT_MODEL = "anthropic/claude-haiku-5.5"

# "none" disables deepseek's reasoning phase (verified: first token ~1.4s vs
# multi-second reasoning; full reasoning pushed real searches to ~40s).
# Set to "low"/"medium"/"high" to re-enable reasoning — the streaming pipeline
# and frontend reasoning panel support it end to end.
REASONING_EFFORT = "low"
