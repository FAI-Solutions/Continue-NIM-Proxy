"""
NIM Proxy v2.0.0 for Continue/VSCodium (Streaming Edition - Final Fix)
Fixes Step 3.7 Flash compatibility by:
    1. Stripping min_p (causes HTTP 400 with speculative decoding)
    2. Stripping reasoning/reasoning_content chunks
    3. Stripping usage from content chunks (Continue breaks otherwise)
    4. Preserving tool_calls chunks so Continue can execute tools
    5. STREAMING: Forwards tokens in real-time while fixing the HTTP/1.1 infinite hang
"""

import http.server
import urllib.request
import urllib.error
import json
import time
import os
import uuid


### CONFIGURATION
DEBUG_MODE = False  # False → debug off ; True → debug on
LISTEN_PORT = 7606
NIM_BASE = "https://integrate.api.nvidia.com/v1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "proxy_logs")


if DEBUG_MODE:
    os.makedirs(LOG_DIR, exist_ok=True)

def log_request_response(req_id, direction, data):
    if not DEBUG_MODE:
        return

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    is_json = False
    parsed_data = None

    try:
        if isinstance(data, bytes):
            parsed_data = json.loads(data.decode('utf-8', errors='ignore'))
            is_json = True
        elif isinstance(data, str):
            parsed_data = json.loads(data)
            is_json = True
    except Exception:
        pass

    ext = "json" if is_json else "txt"
    filename = os.path.join(LOG_DIR, f"{timestamp}_{req_id}_{direction}.{ext}")

    try:
        with open(filename, "w", encoding="utf-8") as f:
            if is_json:
                json.dump(parsed_data, f, indent=2)
            else:
                if isinstance(data, bytes):
                    f.write(data.decode('utf-8', errors='ignore'))
                else:
                    f.write(str(data))
        print(f"[logger] {direction} -> {filename}", flush=True)
    except Exception as e:
        print(f"[logger] Failed to write log: {e}", flush=True)

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if DEBUG_MODE:
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
        req_id = uuid.uuid4().hex[:8]
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
            payload.pop("min_p", None)
            body = json.dumps(payload).encode('utf-8')
        except Exception:
            pass

        if DEBUG_MODE:
            log_request_response(req_id, "request", body)

        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "connection")}
        headers["Content-Length"] = str(len(body))
        headers["Host"] = "integrate.api.nvidia.com"

        req = urllib.request.Request(NIM_BASE + self.path, data=body, headers=headers, method="POST")

        headers_sent = False
        raw_response_buffer = [] if DEBUG_MODE else None

        try:
            with urllib.request.urlopen(req) as resp:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'close')
                self.end_headers()
                headers_sent = True

                for line in resp:
                    if raw_response_buffer is not None:
                        raw_response_buffer.append(line)

                    if line.endswith(b"\r\n"):
                        payload_bytes = line[:-2]
                        newline = b"\r\n"
                    elif line.endswith(b"\n"):
                        payload_bytes = line[:-1]
                        newline = b"\n"
                    else:
                        payload_bytes = line
                        newline = b""

                    if not payload_bytes.startswith(b"data:"):
                        self.wfile.write(line)
                        self.wfile.flush()
                        continue

                    raw_data = payload_bytes[5:].strip()
                    if raw_data == b"[DONE]":
                        self.wfile.write(line)
                        self.wfile.flush()
                        continue

                    try:
                        chunk = json.loads(raw_data)
                        choices = chunk.get("choices", [])
                        delta = choices[0].get("delta", {}) if choices else {}
                        content = delta.get("content")
                        has_reasoning = "reasoning" in delta or "reasoning_content" in delta
                        has_tool_calls = "tool_calls" in delta

                        skip = False
                        if not has_tool_calls:
                            if (content is None or content == "") and has_reasoning:
                                skip = True
                            if content == "" and not has_reasoning:
                                skip = True

                        if skip:
                            continue

                        if choices:
                            delta.pop("reasoning", None)
                            delta.pop("reasoning_content", None)
                            chunk.pop("usage", None)

                        out_payload = b"data: " + json.dumps(chunk).encode('utf-8')
                        self.wfile.write(out_payload + newline)
                        self.wfile.flush()

                    except Exception:
                        self.wfile.write(line)
                        self.wfile.flush()

                if DEBUG_MODE and raw_response_buffer:
                    log_request_response(req_id, "response", b"".join(raw_response_buffer).decode('utf-8', errors='ignore'))

        except urllib.error.HTTPError as e:
            err = e.read()
            if not headers_sent:
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(err)
            else:
                self.wfile.write(f"data: {{\"error\": \"{str(e)}\"}}\n\n".encode('utf-8'))
                self.wfile.flush()
                
        except Exception as e:
            if DEBUG_MODE:
                print(f"[proxy] Streaming error: {e}", flush=True)
            if not headers_sent:
                self.send_error(500, str(e))
            else:
                self.wfile.write(f"data: {{\"error\": \"{str(e)}\"}}\n\n".encode('utf-8'))
                self.wfile.flush()

if __name__ == '__main__':
    print(f"[proxy] NIM proxy running on http://localhost:{LISTEN_PORT}", flush=True)
    if DEBUG_MODE:
        print("[proxy] DEBUG MODE IS ON - Logging to disk", flush=True)
    http.server.HTTPServer(("localhost", LISTEN_PORT), ProxyHandler).serve_forever()