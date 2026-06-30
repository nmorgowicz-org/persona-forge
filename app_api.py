import time
import requests
from flask import Flask, request, jsonify, Response, stream_with_context

app = Flask(__name__)

WORKER_URL = "http://127.0.0.1:8319"


@app.route("/health")
def health():
    try:
        r = requests.get(f"{WORKER_URL}/health", timeout=3)
        r.raise_for_status()
        return jsonify({"status": "ok", "worker": r.json(), "timestamp": time.time()})
    except Exception:
        return (
            jsonify(
                {
                    "status": "degraded",
                    "detail": "API up, worker unreachable",
                    "timestamp": time.time(),
                }
            ),
            503,
        )


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        r = requests.post(
            f"{WORKER_URL}/infer",
            json=data,
            timeout=300,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "Inference timed out (300s)"}), 504
    except requests.RequestException:
        return jsonify({"error": "Worker unreachable"}), 502

    if r.status_code != 200:
        return jsonify({"error": f"Inference error: {r.text[:500]}"}), r.status_code

    return Response(r.content, content_type=r.headers.get("content-type", "audio/mpeg"))


@app.route("/generate/stream", methods=["POST"])
def generate_stream():
    """Proxy the worker's headerless mono f32le PCM stream."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        upstream = requests.post(
            f"{WORKER_URL}/infer_stream",
            json=data,
            stream=True,
            timeout=300,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "Inference timed out (300s)"}), 504
    except requests.RequestException:
        return jsonify({"error": "Worker unreachable"}), 502

    if upstream.status_code != 200:
        detail = upstream.text[:500]
        upstream.close()
        return jsonify({"error": f"Inference error: {detail}"}), upstream.status_code

    def body():
        try:
            yield from upstream.iter_content(chunk_size=64 * 1024)
        finally:
            upstream.close()

    forwarded_headers = {
        name: upstream.headers[name]
        for name in (
            "X-Audio-Format",
            "X-Audio-Sample-Rate",
            "X-Audio-Channels",
            "X-Stream-Error-Semantics",
        )
        if name in upstream.headers
    }
    return Response(
        stream_with_context(body()),
        content_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers=forwarded_headers,
        direct_passthrough=True,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8318)
