"""Throwaway embedding server for the stage 7 bake-off. NOT part of the product.

Serves any sentence-transformers model behind the same `POST /api/embed` shape Ollama uses, so the
product's `OllamaEmbedder` can talk to it unchanged. Run it in the isolated evaluation environment
(never in the product images):

    ~/.local/eval-env/venv/bin/python backend/evals/serve_embedder.py \
        --model intfloat/multilingual-e5-large --port 11500

Vectors are L2-normalized. Query/passage prefixes (e.g. e5's "query: ") are the CLIENT's job, so
the same server can serve queries and passages.
"""

import argparse

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


class EmbedRequest(BaseModel):
    model: str = ""
    input: list[str]


def build(model_name: str, max_seq_length: int) -> FastAPI:
    model = SentenceTransformer(model_name, device="cpu")
    model.max_seq_length = max_seq_length
    app = FastAPI()

    @app.get("/api/version")
    def version() -> dict[str, str]:
        return {"version": f"sentence-transformers:{model_name}"}

    @app.post("/api/embed")
    def embed(request: EmbedRequest) -> dict[str, list[list[float]]]:
        vectors = model.encode(
            request.input, normalize_embeddings=True, batch_size=16, show_progress_bar=False
        )
        return {"embeddings": [[float(x) for x in v] for v in vectors]}

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--max-seq-length", type=int, default=512)
    args = parser.parse_args()
    uvicorn.run(build(args.model, args.max_seq_length), host="127.0.0.1", port=args.port)
