from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import Answers, MatchResponse

app = FastAPI(title="FounderDesk API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok"}

# TODO: /match endpoint after rules engine exists