"""
NIM Proxy for Continue/VSCodium
Fixes Step 3.7 Flash compatibility by:
    1. Stripping min_p (causes HTTP 400 with speculative decoding)
    2. Stripping reasoning/reasoning_content chunks
    3. Stripping usage from content chunks (Continue breaks otherwise)
"""
import http.server
import urllib.request
import urllib.error
import json

LISTEN_PORT = 7606
NIM_BASE = "https://integrate.api.nvidia.com/v1"

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[proxy] {format % args}", flush=True)

    def do_GET(self):
        url = NIM_BASE + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() != 'host'}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
        except Exception as e:
            self.send_error(500, str(e))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
            payload.pop("min_p", None)
            body = json.dumps(payload).encode()
        except Exception:
            pass

        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "connection")}
        headers["Content-Length"] = str(len(body))
        headers["Host"] = "integrate.api.nvidia.com"

        req = urllib.request.Request(NIM_BASE + self.path, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                out_lines = []

                for line in raw.split(b"\n"):
                    if not line.startswith(b"data:"):
                        out_lines.append(line)
                        continue

                    raw_data = line[5:].strip()
                    if raw_data == b"[DONE]":
                        out_lines.append(line)
                        continue

                    try:
                        chunk = json.loads(raw_data)
                        choices = chunk.get("choices", [])
                        delta = choices[0].get("delta", {}) if choices else {}
                        content = delta.get("content")
                        has_reasoning = "reasoning" in delta or "reasoning_content" in delta

                        if (content is None or content == "") and has_reasoning:
                            continue
                        if content == "" and not has_reasoning:
                            continue

                        if choices:
                            delta.pop("reasoning", None)
                            delta.pop("reasoning_content", None)
                            chunk.pop("usage", None)  # usage on content chunks breaks Continue

                        out_lines.append(b"data: " + json.dumps(chunk).encode())
                    except Exception:
                        out_lines.append(line)

                response_body = b"\n".join(out_lines)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.send_header('Content-Length', str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
                self.wfile.flush()

        except urllib.error.HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(err)
        except Exception as e:
            self.send_error(500, str(e))

print(f"[proxy] NIM proxy running on http://localhost:{LISTEN_PORT}", flush=True)
http.server.HTTPServer(("localhost", LISTEN_PORT), ProxyHandler).serve_forever()
