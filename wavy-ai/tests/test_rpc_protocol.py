"""
Tests for the ZeroMQ JSON-RPC protocol layer.
These tests spin up a real server and send raw JSON messages.
"""

from __future__ import annotations

import json
import pytest
from .conftest import rpc_call


class TestHealthEndpoint:
    def test_health_returns_ok(self, ai_server, zmq_client):
        resp = rpc_call(zmq_client, "health")
        assert resp["result"]["status"] == "ok"

    def test_health_includes_version(self, ai_server, zmq_client):
        resp = rpc_call(zmq_client, "health")
        assert "version" in resp["result"]

    def test_health_includes_loaded_models(self, ai_server, zmq_client):
        resp = rpc_call(zmq_client, "health")
        assert isinstance(resp["result"]["loaded_models"], list)


class TestProtocolEdgeCases:
    def test_unknown_method_returns_error(self, ai_server, zmq_client):
        resp = rpc_call(zmq_client, "totally_unknown_method")
        assert "error" in resp
        assert "totally_unknown_method" in resp["error"]

    def test_id_is_echoed(self, ai_server, zmq_client):
        req = json.dumps({"id": 42, "method": "health", "params": {}})
        zmq_client.send(req.encode())
        raw = zmq_client.recv()
        resp = json.loads(raw.decode())
        assert resp["id"] == 42

    def test_malformed_json_returns_error(self, ai_server, zmq_client):
        zmq_client.send(b"not json {{{{")
        raw = zmq_client.recv()
        resp = json.loads(raw.decode())
        assert "error" in resp
        assert resp["id"] is None

    def test_missing_params_defaults_gracefully(self, ai_server, zmq_client):
        # health has no required params — should still succeed
        req = json.dumps({"id": 1, "method": "health"})
        zmq_client.send(req.encode())
        resp = json.loads(zmq_client.recv().decode())
        assert "result" in resp


class TestModelListing:
    def test_list_models_returns_all(self, ai_server, zmq_client):
        resp = rpc_call(zmq_client, "list_models")
        models = resp["result"]["models"]
        names = {m["name"] for m in models}
        assert "demucs" in names
        assert "mixer" in names

    def test_list_models_includes_vram(self, ai_server, zmq_client):
        resp = rpc_call(zmq_client, "list_models")
        for m in resp["result"]["models"]:
            assert "vram_gb" in m
            assert isinstance(m["vram_gb"], (int, float))
