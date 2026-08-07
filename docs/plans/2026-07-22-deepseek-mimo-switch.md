# DeepSeek + MiMo Model Pair

## Goal

Use DeepSeek for primary write scenes and MiMo for reasoning-heavy audit scenes,
replacing the active Claude pairing without removing the generic Anthropic runner.

## Configuration

- Primary model: `deepseek-v4-pro`
- Audit model: `mimo-v2.5-pro-thinking`
- MiMo endpoint: `https://api.xiaomimimo.com/v1/chat/completions`
- Credential: `MIMO_API_KEY` from the process environment only

No API key is stored in Git, model catalog JSON, run summaries, or preflight
output.

## Verification

1. Run write preflight for the DeepSeek + MiMo pair.
2. Exercise MiMo non-streaming and streaming text responses.
3. Exercise MiMo tool-call streaming through the shared runner contract.
4. Run focused and full regressions, Ruff, Pyright, and diff checks.
5. Ask both DeepSeek and MiMo for independent read-only review.
