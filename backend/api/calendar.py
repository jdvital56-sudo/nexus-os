"""Calendar API routes."""
from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
from ..services import calendar as svc
from ..core.auth import get_token_dep

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
auth = get_token_dep()


@router.get("/status")
def status(_=Depends(auth)):
    return {"configured": svc.is_configured(), "instructions": svc.setup_instructions() if not svc.is_configured() else None}


@router.get("/events")
def get_events(days: int = 7, max_results: int = 20, _=Depends(auth)):
    try:
        events = svc.get_upcoming_events(days=days, max_results=max_results)
    except svc.CalendarAuthExpired as e:
        # 503, а не пустой список: человек должен увидеть причину и пойти
        # переподключить Google, а не решить, что у него нет встреч
        raise HTTPException(status_code=503, detail=str(e))
    svc.cache_events(events)
    return {"count": len(events), "events": events}


@router.post("/sync")
def sync_to_graph(days: int = 7, _=Depends(auth)):
    events = svc.get_upcoming_events(days=days)
    svc.cache_events(events)
    result = svc.sync_events_to_graph(events)
    return result


class TaskToEventRequest(BaseModel):
    task_id: str | None = None
    title: str = ""
    description: str = ""
    duration_minutes: int = 60


@router.post("/create-event")
def create_event(req: TaskToEventRequest, _=Depends(auth)):
    if req.task_id:
        from ..services import tasks as task_svc
        try:
            task = task_svc.get_task(req.task_id)
            event = svc.create_event_from_task(task.model_dump(), req.duration_minutes)
            if event:
                return {"created": True, "event": event}
            return {"created": False, "reason": "Calendar not configured"}
        except Exception as e:
            return {"created": False, "error": str(e)}

    event = svc.create_event_from_task({"title": req.title, "description": req.description}, req.duration_minutes)
    if event:
        return {"created": True, "event": event}
    return {"created": False, "reason": "Calendar not configured"}
