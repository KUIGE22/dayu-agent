# Anthropic Native Streaming

## Goal

Enable native Anthropic Messages API streaming without duplicating Dayu's HTTP,
retry, cancellation, tool execution, or completion-event governance.

## Design

1. Add a protected SSE parser factory to `AsyncOpenAIRunner`; its default keeps
   the existing OpenAI-compatible parser unchanged.
2. Implement an Anthropic parser that reuses the shared SSE framing and maps
   native message, content, tool-input, thinking, stop, error, and usage events
   into the existing `SSEParseResult` contract.
3. Keep unknown Anthropic event and delta types forward-compatible by ignoring
   them. Malformed known events remain protocol errors.
4. Let the shared Runner continue to own tool execution, final content, DONE,
   metadata, retries, cancellation, and trace annotations.
5. Enable streaming in the Claude catalog and factory only after parser tests
   pass, then verify against the configured live Claude endpoint.

## Verification

- Payload and parser unit tests for text, thinking, tool JSON, usage, stop, and
  in-stream error events.
- Existing OpenAI-compatible SSE regression tests.
- Live Claude streaming smoke test through ConfigLoader, Agent Builder, and
  Runner Factory.
- Ruff, Pyright, focused tests, full regression, and read-only Claude/DeepSeek
  review.
