from fastapi import APIRouter

from app.api.routes import (
    adjudications,
    admin,
    analysis,
    audit,
    auth,
    candidates,
    cases,
    documents,
    evaluations,
    exports,
    health,
    rubrics,
    selection,
    users,
    workflow,
    workflow_plan,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(documents.router, prefix="/cases/{case_id}/documents", tags=["documents"])
api_router.include_router(audit.router, prefix="/cases/{case_id}/audit-events", tags=["audit"])
api_router.include_router(candidates.router, prefix="/cases/{case_id}/candidates", tags=["candidates"])
api_router.include_router(analysis.router, prefix="/cases/{case_id}/analysis", tags=["analysis"])
api_router.include_router(rubrics.router, prefix="/cases/{case_id}/rubrics", tags=["rubrics"])
api_router.include_router(workflow.router, prefix="/cases/{case_id}/workflow", tags=["workflow"])
api_router.include_router(evaluations.router, prefix="/cases/{case_id}/evaluations", tags=["evaluations"])
api_router.include_router(selection.router, prefix="/cases/{case_id}/selection", tags=["selection"])
api_router.include_router(adjudications.router, prefix="/cases/{case_id}/adjudications", tags=["adjudications"])
api_router.include_router(exports.router, prefix="/cases/{case_id}/exports", tags=["exports"])
api_router.include_router(workflow_plan.router, prefix="/cases/{case_id}", tags=["workflow-plan"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(users.router, prefix="/admin/users", tags=["users"])
