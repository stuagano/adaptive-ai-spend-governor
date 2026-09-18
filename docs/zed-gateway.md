# Use the local gateway in Zed

This setup connects Zed's built-in Agent to the project's loopback proxy, then to
the Gemini model service through Unity Gateway. It does not configure external
agents, terminal threads, or edit predictions.

## Start the proxy

From this repository, authenticate with the selected workspace profile:

```sh
databricks auth login --profile fevm
```

Keep the proxy running in a terminal:

```sh
export GATEWAY_POLICY_SESSION_SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
.venv/bin/gateway-policy proxy run local-policy.yaml \
  --policy-name central-session --profile fevm --require-session \
  --port 8081 --state-path .gateway-policy/zed-state.db
```

The profile's workspace host must match the policy's upstream host. OAuth stays
in the proxy; Zed receives only a signed, limited-lifetime session credential.
The existing proxy on port 8080 is independent of this setup.

The local policy uses the model service `system.ai.gemini-3-8-flash` and an
upstream base ending in `/ai-gateway/cursor`, not `/serving-endpoints/...`.
The service advertises `cursor/v1/chat/completions`; this route emits the text
content expected by an OpenAI-compatible coding client.

## Configure Zed

Add this provider to the existing `language_models.openai_compatible` settings.
Do not replace unrelated settings or put credentials in the file.

```json
{
  "company-gateway": {
    "api_url": "http://127.0.0.1:8081/v1",
    "available_models": [
      {
        "name": "system.ai.gemini-3-8-flash",
        "display_name": "Gemini 3.8 Flash — Company Gateway",
        "max_tokens": 32768,
        "max_output_tokens": 4096,
        "capabilities": {
          "tools": true,
          "images": false,
          "parallel_tool_calls": false,
          "prompt_cache_key": false,
          "chat_completions": true,
          "interleaved_reasoning": false,
          "max_tokens_parameter": true
        }
      }
    ]
  }
}
```

The 32,768-token context setting is a conservative local client limit, not a
claim about the model's maximum context window. Images, parallel tool calls,
and reasoning controls are not enabled or certified by this setup.

## Create or renew the credential

In a second terminal on macOS, create a session and copy its credential directly
to the clipboard without printing it:

```sh
set -o pipefail
curl --fail --silent --show-error http://127.0.0.1:8081/sessions \
  -H 'Content-Type: application/json' \
  --data '{"policy_name":"central-session","identity":"local-zed-user","project":"zed"}' \
  | .venv/bin/python -c 'import json,sys; sys.stdout.write(json.load(sys.stdin)["session_token"])' \
  | pbcopy
```

In Zed, open `agent: open settings`, find `company-gateway` under LLM Providers,
and paste into its API-key field. Select **Gemini 3.8 Flash — Company Gateway**
in the Agent model picker, then start a new thread. Zed stores the credential
in the system keychain. A nonempty `COMPANY_GATEWAY_API_KEY` environment variable
takes precedence; unset it and restart Zed if it overrides the saved credential.

The local session lasts one hour and has the USD/token allowances in
`local-policy.yaml`. Renew it with the same command. Start a new thread after
changing sessions: Gemini tool signatures are deliberately isolated by session.
Restarting the proxy with a new signing secret invalidates older credentials.

## Compatibility and verification

- The proxy keeps upstream OAuth separate from the session bearer token.
- Streaming stays open until the upstream completes, buffers split SSE lines,
  tolerates nullable usage fields, and preserves upstream HTTP error status.
- Gemini's `extra_content.google.thought_signature` is retained in session-scoped
  state and restored when a client returns a tool call without provider fields.
  A fingerprint binds the saved signature to its original function and arguments.
- Protocol metadata uses a separate key namespace in the existing state store;
  it is not shared between sessions or logged as part of this integration.
- Focused regression tests are in `tests/test_zed_proxy.py`. Live verification
  must include a streamed tool call **and its tool-result continuation**; a
  successful greeting alone does not establish Agent compatibility.

This is a local development connection, not a corporate onboarding deployment.
Keep it bound to loopback: session creation trusts the local caller. The policy's
configured model prices are estimates and must be verified before relying on
USD accounting. A full Zed Agent workflow still needs an interactive smoke test.
