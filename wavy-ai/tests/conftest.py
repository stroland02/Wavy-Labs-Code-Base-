"""
Shared pytest fixtures for the wavy-ai test suite.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Generator

import pytest
import zmq

# ── Make sure wavy-ai root is on sys.path ─────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import WavyAIServer

TEST_PORT = 15555  # isolated port so tests don't clash with a running server


@pytest.fixture(scope="session")
def ai_server() -> Generator[WavyAIServer, None, None]:
    """Start a real WavyAIServer on TEST_PORT for the session."""
    server = WavyAIServer(host="127.0.0.1", port=TEST_PORT)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    time.sleep(0.3)     # let the REP socket bind
    yield server
    server.stop()


@pytest.fixture(scope="session")
def zmq_client() -> Generator[zmq.Socket, None, None]:
    """ZeroMQ REQ socket connected to the test server."""
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.set(zmq.RCVTIMEO, 10_000)
    sock.set(zmq.SNDTIMEO, 5_000)
    sock.connect(f"tcp://127.0.0.1:{TEST_PORT}")
    yield sock
    sock.close()
    ctx.term()


def rpc_call(sock: zmq.Socket, method: str, params: dict = {}) -> dict:
    """Send a JSON-RPC request and return the parsed response."""
    req = json.dumps({"id": 1, "method": method, "params": params})
    sock.send(req.encode())
    raw = sock.recv()
    return json.loads(raw.decode())


# ── Tiny silence .wav fixture ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def silence_wav(tmp_path_factory) -> Path:
    """Generate a 1-second 44.1 kHz silence WAV for model tests."""
    import soundfile as sf
    import numpy as np
    p = tmp_path_factory.mktemp("fixtures") / "silence.wav"
    sf.write(str(p), np.zeros((44100, 2), dtype=np.float32), 44100)
    return p
