# IPC Protocol

The C++/Qt6 UI communicates with the Python AI backend over a **ZeroMQ REQ/REP**
socket on `tcp://127.0.0.1:5555` using **JSON-RPC 2.0**.

## Request Format

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "generate_music",
  "params": {
    "prompt": "Lo-fi hip hop with jazz chords",
    "duration": 30,
    "tempo": 90,
    "model": "ace_step"
  }
}
```

## Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "audio_path": "/tmp/wavy/gen_20240301_143022.wav",
    "duration": 30.4
  }
}
```

## Error Response

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "error": {
    "code": -32603,
    "message": "Model not loaded: ace_step"
  }
}
```

## Error Codes

| Code | Meaning |
|------|---------|
| `-32700` | Parse error |
| `-32600` | Invalid request |
| `-32601` | Method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |

---

## Transport

- **Socket type:** ZeroMQ REQ (C++) / REP (Python)
- **Serialization:** JSON (UTF-8)
- **Timeout:** 120 000 ms (C++ client default, configurable)
- **Concurrency:** The Python server processes one request at a time (single REP socket).
  The C++ client queues concurrent requests and sends them sequentially.

---

## C++ Client (`AIClient`)

`wavy-ui/IPC/AIClient.cpp`

```cpp
// Singleton access
AIClient* client = AIClient::instance();

// Async call
client->generateMusic(params,
    [](bool ok, const QVariantMap& result) {
        if (ok) qDebug() << result["audio_path"];
    });
```

All callbacks are delivered on the calling thread's event loop via
`QMetaObject::invokeMethod(..., Qt::QueuedConnection)`.

---

## Python Server (`server.py`)

```bash
cd wavy-ai
python server.py --port 5555 --log-level INFO
```

The server loads handlers from `rpc_handlers.py` which maps each method name
to a Python callable.
