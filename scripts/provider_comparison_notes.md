
**OpenAI**
- System prompt: just another message in the list, with `role: "system"` (or `"developer"` in newer models) — no separate field.
- Plain text call: `client.chat.completions.create(messages=...)`, text is at `response.choices[0].message.content`.
- Tool call: check `response.choices[0].message.tool_calls` — a list, each item has `.function.name` and `.function.arguments` (arguments come back as a JSON *string*, not a dict, so you'd need to `json.loads()` it).
- Streaming: `stream=True`, iterate chunks, text is at `chunk.choices[0].delta.content` (can be `None`, needs a guard).

**Anthropic**
- System prompt: its own top-level parameter — `system="..."` passed alongside `messages`, not inside the messages list at all. This is the biggest structural difference from OpenAI.
- Plain text call: `client.messages.create(messages=...)`, text is at `response.content[0].text`.
- Tool call: `response.stop_reason == "tool_use"`, and the tool call itself is a `ToolUseBlock` inside the `content` list, with `.name`, `.input` (already a dict, not a string), and `.id` (needed to match the result back).
- Streaming: `client.messages.stream(...)` used as a context manager, iterate events, filter `event.type == "content_block_delta"`, text is at `event.delta.text`.

**Gemini** (per today's quickstart)
- Plain text call: `client.interactions.create(model=..., input="...")`, text is at `interaction.output_text`.
- System prompt / tool calls / streaming for this specific `interactions` API: you didn't test these yet, so mark as "not yet tested" honestly — I don't want to guess at the exact field names for an API this newly restructured and have it be wrong in your reference note. Worth a 5-minute docs check before you rely on it tomorrow.
