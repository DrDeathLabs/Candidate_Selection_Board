from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException, status

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.ai_inference import AIGatewayService, GatewayInvocationRequest, GatewayInvocationResponse

settings = get_settings()
app = FastAPI(title="Candidate Selection Board AI Gateway", version="0.1.0")
gateway_service = AIGatewayService()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-gateway"}


@app.post("/v1/invoke")
def invoke_model(request: GatewayInvocationRequest) -> GatewayInvocationResponse:
    with SessionLocal() as db:
        try:
            return gateway_service.invoke(db, request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
