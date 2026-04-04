"""
Wavy Labs AI Backend — ZeroMQ JSON-RPC server
============================================
Entry point for the Python AI backend process.

Protocol
--------
- Transport : ZeroMQ REP socket, TCP, localhost:5555
- Encoding  : JSON
- Request   : {"id": <int>, "method": <str>, "params": <dict>}
- Response  : {"id": <int>, "result": <any>}   on success
            | {"id": <int>, "error":  <str>}   on failure

Usage
-----
    python server.py [--port 5555] [--log-level DEBUG]
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import queue
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

# Force UTF-8 stdout/stderr on Windows (default is cp1252 which can't encode
# many Unicode chars used in log output, causing crashes in print()).
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# On Windows, add DLL search paths before any native imports.
if sys.platform == "win32":
    # MSYS2/MinGW — needed by llama-cpp-python
    _msys2_bin = r"C:\msys64\mingw64\bin"
    if os.path.isdir(_msys2_bin):
        os.add_dll_directory(_msys2_bin)
    # PyTorch CUDA runtime DLLs (bundled in torch/lib/)
    _torch_lib = os.path.join(sys.prefix, "Lib", "site-packages", "torch", "lib")
    if os.path.isdir(_torch_lib):
        os.add_dll_directory(_torch_lib)

# Embedded Python's ._pth file overrides normal script-directory sys.path
# insertion. Ensure wavy-ai/ is always on sys.path so local modules import.
_server_dir = os.path.dirname(os.path.abspath(__file__))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

import re

import zmq
from loguru import logger

import config
from config import HOST, PORT
from crash_reporter import init_sentry
from models.registry import ModelRegistry
from rpc_handlers import RPC_HANDLERS


def _clean_error(exc: Exception) -> str:
    """Extract a user-friendly message from an exception.

    ElevenLabs SDK exceptions embed full HTTP response headers + body in
    their str() representation.  Parse out just the actionable message.
    """
    raw = str(exc)

    # Try to pull a JSON body out of the raw string
    # EL SDK format: "... body: {'detail': {'status': '...', 'message': '...'}}"
    # or            "... body: {'detail': '...'}"
    try:
        # Grab the last {...} blob which is typically the response body
        brace_match = re.search(r"\{.*\}$", raw, re.DOTALL)
        if brace_match:
            import ast
            body = ast.literal_eval(brace_match.group())
            detail = body.get("detail") or body.get("error") or body
            if isinstance(detail, dict):
                status  = detail.get("status", "")
                message = detail.get("message", "")
                if message:
                    prefix = f"ElevenLabs [{status}]: " if status else "ElevenLabs: "
                    return prefix + message
            if isinstance(detail, str) and detail:
                return "ElevenLabs: " + detail
    except Exception:
        pass

    # Fallback: keep only the first line (before headers dump)
    first_line = raw.split("\n")[0].strip()
    # Strip HTTP header noise (lines starting with "headers:")
    if first_line.lower().startswith("headers:"):
        # Try to find status_code / body further in
        m = re.search(r"'message':\s*'([^']+)'", raw)
        if m:
            return "ElevenLabs: " + m.group(1)
        m = re.search(r"status_code:\s*(\d+)", raw)
        return f"ElevenLabs API error (HTTP {m.group(1)})" if m else "ElevenLabs API error"
    return first_line or "Unknown error"

# ── Logging ──────────────────────────────────────────────────────────────────

def _configure_logging(level: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level=level,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")


# ── Server ───────────────────────────────────────────────────────────────────

class WavyAIServer:
    """ZeroMQ ROUTER server that dispatches JSON-RPC calls to model handlers.

    Uses a ROUTER socket + ThreadPoolExecutor so heavy operations (demucs,
    ElevenLabs dubbing, music generation) run in background threads while
    lightweight calls (health, set_session_context) are served concurrently.
    """

    # Methods that are fast enough to run inline (< 1s)
    _LIGHTWEIGHT = frozenset({
        "health", "startup_check", "list_models", "set_session_context",
        "load_personas", "save_persona", "get_instrument_choices",
        "midicaps_library_status", "elevenlabs_list_voices",
        "list_soundfonts",
    })

    def __init__(self, host: str = "127.0.0.1", port: int = 5555,
                 max_workers: int = 4) -> None:
        self._endpoint = f"tcp://{host}:{port}"
        self._ctx = zmq.Context()
        self._socket: zmq.Socket | None = None
        self._running = False
        self._registry = ModelRegistry()
        self._pool = ThreadPoolExecutor(max_workers=max_workers,
                                        thread_name_prefix="rpc-worker")
        self._results: queue.Queue = queue.Queue()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._socket = self._ctx.socket(zmq.ROUTER)
        self._socket.bind(self._endpoint)
        self._running = True
        logger.info(f"Wavy Labs AI backend listening on {self._endpoint} "
                     f"(workers={self._pool._max_workers})")
        self._loop()

    def stop(self) -> None:
        self._running = False
        self._pool.shutdown(wait=False)
        if self._socket:
            self._socket.close()
        self._ctx.term()
        logger.info("AI backend stopped.")

    # ── Main loop ────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self._socket, zmq.POLLIN)

        while self._running:
            # Drain completed background results first
            while not self._results.empty():
                try:
                    identity, response = self._results.get_nowait()
                    self._send_response(identity, response)
                except queue.Empty:
                    break

            try:
                ready = dict(poller.poll(timeout=100))
            except zmq.ZMQError:
                break  # socket was closed by stop()

            if self._socket not in ready:
                continue

            # ROUTER socket: [identity, empty, payload]
            frames = self._socket.recv_multipart()
            if len(frames) < 3:
                continue
            identity = frames[0]
            raw = frames[-1]

            request, req_id, method, params = self._parse_request(raw)
            if request is None:
                self._send_response(identity, {"id": req_id, "error": method})
                continue

            # Validate params
            error = self._validate_params(req_id, method, params)
            if error:
                self._send_response(identity, error)
                continue

            handler = RPC_HANDLERS.get(method)
            if handler is None:
                self._send_response(identity,
                                     {"id": req_id, "error": f"Unknown method: {method}"})
                continue

            if method in self._LIGHTWEIGHT:
                # Run inline — fast path
                response = self._run_handler(req_id, method, handler, params)
                self._send_response(identity, response)
            else:
                # Offload to thread pool — heavy path
                self._pool.submit(self._run_handler_async,
                                   identity, req_id, method, handler, params)

    def _send_response(self, identity: bytes, response: Dict[str, Any]) -> None:
        try:
            self._socket.send_multipart([
                identity, b"", json.dumps(response).encode()
            ])
        except zmq.ZMQError as e:
            logger.warning(f"Failed to send response: {e}")

    def _parse_request(self, raw: bytes):
        """Parse raw bytes into (request_dict, id, method, params) or error."""
        try:
            request = json.loads(raw.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return None, None, f"Parse error: {exc}", {}

        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})
        logger.debug(f"RPC → {method}({params})")
        return request, req_id, method, params

    def _validate_params(self, req_id, method, params) -> Dict[str, Any] | None:
        """Validate params; return error dict or None if valid."""
        if not isinstance(params, dict):
            return {"id": req_id, "error": "params must be a JSON object"}

        try:
            from rpc_handlers import _validate_path
            for key, val in params.items():
                if key.endswith("_path") and isinstance(val, str) and val:
                    _validate_path(val, key)
                elif key.endswith("_paths") and isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and v:
                            _validate_path(v, key)
        except ValueError as exc:
            return {"id": req_id, "error": str(exc)}

        return None

    def _run_handler(self, req_id, method, handler, params) -> Dict[str, Any]:
        try:
            result = handler(params, self._registry)
            return {"id": req_id, "result": result}
        except Exception as exc:
            logger.exception(f"Handler {method} raised: {exc}")
            return {"id": req_id, "error": _clean_error(exc)}

    def _run_handler_async(self, identity, req_id, method, handler, params):
        """Run handler in thread pool and enqueue result for main loop."""
        response = self._run_handler(req_id, method, handler, params)
        self._results.put((identity, response))


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Wavy Labs AI backend server")
    p.add_argument("--host",      default=HOST)
    p.add_argument("--port",      type=int, default=PORT)
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    _configure_logging(args.log_level)
    init_sentry()

    logger.info(f"Cloud provider: {config.CLOUD_PROVIDER}")
    logger.info(f"Registered methods ({len(RPC_HANDLERS)}): {', '.join(sorted(RPC_HANDLERS))}")

    server = WavyAIServer(host=args.host, port=args.port)

    def _on_signal(sig, _frame):
        logger.info(f"Signal {sig} received — shutting down …")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    server.start()


if __name__ == "__main__":
    main()
