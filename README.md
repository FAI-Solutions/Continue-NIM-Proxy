# NIM Proxy for Step 3.7 Flash in Continue/VSCodium

Fixes **Step 3.7 Flash** silently returning empty responses in [Continue](https://continue.dev/).

**Root Cause**: Step 3.7 Flash on NVIDIA NIM runs with speculative decoding and includes a `usage` field on **every** streaming chunk. Continue's OpenAI provider interprets any chunk containing `usage` as the final chunk and stops — discarding all content silently, no error shown.

## Overview of the Proxy: 

Sits between Continue and NIM, fixing things per request:

1. **Strips `min_p`** from outgoing requests (causes silent HTTP 400)
2. **Strips `usage`** from content chunks in the streaming response (causes silent empty reply)
3. **Strips `reasoning`/`reasoning_content`** chunks (they had empty content)

## Requirements

- Python 3 (only standard libraries — tested with python 3.14)
- NVIDIA NIM API key

## Setup

**0. Download the proxy**
```
nim_proxy.py
```

**1. Setup the port you want to use**

open `nim_proxy.py` and change the port by replacing the default `LISTEN_PORT = 7606` 7606 with whatever you want to use.


**2. Run the proxy** (keep this terminal open while using STep 3.7 Flash in Continue)
```bash
# source your venv if you use one, then run
python nim_proxy.py
```

**3. Point Continue to the proxy** in your `config.yaml`, here an example of configuration (pay attention to **apiBase**):
```yaml
models:
  - name: Step-3.7-Flash
    provider: openai
    model: stepfun-ai/step-3.7-flash
    apiBase: http://localhost:7606   # important: proxy, not NIM directly
    apiKey: your-nim-key-here
    roles:
      - chat
      - edit
      - apply
      - summarize
    capabilities:
      - tool_use
    requestOptions:
      nvext:
        max_thinking_tokens: 8192
    defaultCompletionOptions:
      temperature: 0.50
      top_p: 0.95
      top_k: 30
      contextLength: 262144
      maxTokens: 16384
    chatOptions:
      baseSystemMessage: |
        You are an expert ... # enter your system prompt here
```

---

## Contact

- **Developer**: Johannes Faber — [fais.udder466@passinbox.com](mailto:fais.udder466@passinbox.com)
- **Hub-Website**: <a href="https://fai-solutions.github.io/" rel="me noopener">https://fai-solutions.github.io/</a>
- **Issues**: <a href="https://github.com/FAI-Solutions/Continue-NIM-Proxy/issues" rel="me noopener">https://github.com/FAI-Solutions/Continue-NIM-Proxy/issues</a>


## Contact

MIT


## Keywords

step-3.7-flash empty response, NIM reasoning model silent failure,
Continue VSCode no reply, continue.dev blank response NIM,
nvidia nim continue vscode not working,
stepfun-ai step-3.7-flash not working Continue,
stepfun step-3.7-flash no reply vscode,
NVIDIA NIM streaming usage field Continue bug,
min_p speculative decoding HTTP 400 NIM
