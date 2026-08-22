"""
Telephony API - J.A.R.V.I.S. Phone Integration
Endpoints for outbound calls, incoming webhooks, and PIN authentication

Low-cost stack: Vapi.ai (free 1000 mins) + Twilio ($15 trial credit)
"""

import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from ..core.auth import get_token_dep
from ..services.telephony_client import telephony_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/call", tags=["telephony"])
auth = get_token_dep()


def _verify_webhook_secret(request: Request) -> bool:
    """Vapi/Twilio не умеют слать наш Bearer-токен — это они зовут нас, не
    мы их (см. общий приём `_verify_query_token` в voice.py для того же
    класса проблемы). Секрет кладётся в URL вебхука при настройке в
    консоли Vapi/Twilio: /api/call/webhook/incoming?secret=...

    Найдено код-ревью 20.08.2026: этих двух ручек не касался вообще
    никакой auth — кто угодно с сетевым доступом мог слать поддельные
    callId/callerId/pinCode напрямую, в обход настоящего звонка и лимита
    попыток PIN (тот считается по caller_id из тела запроса, который
    ничем не проверялся).
    """
    expected = os.getenv("TELEPHONY_WEBHOOK_SECRET", "")
    if not expected:
        # Не настроено — телефония и так не работает без VAPI/TWILIO
        # ключей, но явно предупреждаем в логе, а не молча пропускаем.
        logger.warning(
            "TELEPHONY_WEBHOOK_SECRET не задан — вебхук телефонии "
            "не защищён от поддельных запросов"
        )
        return True
    provided = request.query_params.get("secret", "")
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    return True


# ==================== REQUEST/RESPONSE MODELS ====================

class InitiateCallRequest(BaseModel):
    """Request to initiate outbound call"""
    to_number: str = Field(..., description="Destination phone number (E.164 format: +1234567890)")
    assistant_id: Optional[str] = Field(None, description="Vapi assistant ID (uses default if not provided)")
    model_override: Optional[str] = Field(None, description="Override LLM model (e.g., 'llama-3.3-70b')")


class InitiateCallResponse(BaseModel):
    """Response with call details"""
    success: bool
    call_id: str
    status: str
    to_number: str
    message: str


class PinSubmissionRequest(BaseModel):
    """PIN code submission from caller"""
    call_id: str
    caller_id: str
    pin_code: str


class CallStatusResponse(BaseModel):
    """Current call status"""
    call_id: str
    status: str
    direction: str
    started_at: Optional[str]
    ended_at: Optional[str]
    authenticated: bool = False


class UsageStatsResponse(BaseModel):
    """Telephony usage statistics"""
    provider: str
    total_minutes: int
    remaining_free_minutes: int
    active_calls: int


# ==================== ENDPOINTS ====================

@router.post("/initiate", response_model=InitiateCallResponse)
async def initiate_call(request: InitiateCallRequest, _=Depends(auth)):
    """
    Initiate outbound call via J.A.R.V.I.S.
    
    Example use case: Call auto service to schedule oil change
    
    **Cost**: ~$0.02/min (Twilio) + free (Vapi/Groq tier)
    """
    try:
        result = await telephony_client.create_outbound_call(
            to_number=request.to_number,
            assistant_id=request.assistant_id,
            model_override=request.model_override
        )
        
        return InitiateCallResponse(
            success=True,
            call_id=result.get("id", "unknown"),
            status=result.get("status", "initiated"),
            to_number=request.to_number,
            message=f"Call initiated to {request.to_number}. J.A.R.V.I.S. will handle the conversation."
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to initiate call: {e}")
        raise HTTPException(status_code=500, detail=f"Call initiation failed: {str(e)}")


@router.post("/{call_id}/end")
async def end_call_endpoint(call_id: str, _=Depends(auth)):
    """Terminate an active call"""
    try:
        result = await telephony_client.end_call(call_id)
        return {
            "success": True,
            "call_id": call_id,
            "status": "ended",
            "message": "Call terminated successfully"
        }
    except Exception as e:
        logger.error(f"Failed to end call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to end call: {str(e)}")


@router.get("/{call_id}", response_model=CallStatusResponse)
async def get_call_status(call_id: str, _=Depends(auth)):
    """Get detailed status of a specific call"""
    try:
        details = await telephony_client.get_call_details(call_id)
        
        # Merge with tracked state
        tracked = telephony_client.active_calls.get(call_id, {})
        
        return CallStatusResponse(
            call_id=call_id,
            status=details.get("status", tracked.get("status", "unknown")),
            direction=tracked.get("direction", "unknown"),
            started_at=tracked.get("started_at"),
            ended_at=tracked.get("ended_at"),
            authenticated=tracked.get("status") == "authenticated"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to get call status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve call status: {str(e)}")


@router.get("/active", response_model=List[CallStatusResponse])
async def list_active_calls(_=Depends(auth)):
    """List all currently active calls"""
    active = telephony_client.list_active_calls()
    
    return [
        CallStatusResponse(
            call_id=call.get("call_id", "unknown"),
            status=call.get("status", "unknown"),
            direction=call.get("direction", "unknown"),
            started_at=call.get("started_at"),
            ended_at=call.get("ended_at"),
            authenticated=call.get("status") == "authenticated"
        )
        for call in active
    ]


@router.post("/webhook/incoming")
async def handle_incoming_call_webhook(
    request: Request, background_tasks: BackgroundTasks, _=Depends(_verify_webhook_secret)
):
    """
    Webhook endpoint for incoming calls from Vapi/Twilio
    
    Flow:
    1. Receive incoming call event
    2. Prompt caller for PIN
    3. On success: Transfer to J.A.R.V.I.S. assistant
    4. On failure: Hangup after max attempts
    
    Security: PIN verification with rate limiting
    """
    try:
        data = await request.json()
        call_id = data.get("callId") or data.get("call_id")
        caller_id = data.get("callerId") or data.get("from")
        
        if not call_id or not caller_id:
            raise HTTPException(status_code=400, detail="Missing callId or callerId")
        
        # Process incoming call webhook
        response = await telephony_client.handle_incoming_call_webhook(
            caller_id=caller_id,
            call_id=call_id
        )
        
        logger.info(f"Incoming call from {caller_id} - awaiting PIN")
        return response
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        # Don't expose internal errors to webhook caller
        return {"error": "Processing failed"}


@router.post("/webhook/pin")
async def handle_pin_submission(request: Request, _=Depends(_verify_webhook_secret)):
    """
    Webhook endpoint for PIN code submission
    
    Validates PIN and either:
    - Connects to J.A.R.V.I.S. (on success)
    - Prompts retry or hangs up (on failure)
    """
    try:
        data = await request.json()
        call_id = data.get("callId") or data.get("call_id")
        caller_id = data.get("callerId") or data.get("from")
        pin_input = data.get("pinCode") or data.get("Digits")  # Twilio uses 'Digits'
        
        if not all([call_id, caller_id, pin_input]):
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        response = await telephony_client.handle_pin_submission(
            call_id=call_id,
            caller_id=caller_id,
            pin_input=pin_input
        )
        
        status = "success" if response.get("transferToAssistant") else "failed"
        logger.info(f"PIN submission from {caller_id}: {status}")
        return response
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"PIN submission error: {e}")
        return {"error": "Processing failed"}


@router.get("/usage", response_model=UsageStatsResponse)
async def get_usage_stats(_=Depends(auth)):
    """Get telephony usage statistics (for monitoring billing)"""
    stats = await telephony_client.get_usage_stats()
    
    return UsageStatsResponse(
        provider=stats.get("provider", "Unknown"),
        total_minutes=stats.get("total_minutes", 0),
        remaining_free_minutes=stats.get("remaining_free_minutes", 1000),
        active_calls=stats.get("active_calls", 0)
    )


@router.get("/setup-guide")
async def get_setup_guide(_=Depends(auth)):
    """Return detailed setup instructions for telephony integration"""
    return {
        "instructions": telephony_client.get_setup_instructions(),
        "env_variables": {
            "VAPI_API_KEY": "Your Vapi.ai API key",
            "VAPI_DEFAULT_ASSISTANT_ID": "Default assistant for outbound calls",
            "VAPI_JARVIS_ASSISTANT_ID": "J.A.R.V.I.S. personality assistant",
            "TWILIO_ACCOUNT_SID": "Twilio Account SID",
            "TWILIO_AUTH_TOKEN": "Twilio Auth Token",
            "TWILIO_PHONE_NUMBER": "Your Twilio phone number (+E.164)",
            "CALL_PIN_HASH": "SHA256 hash of your 5-digit PIN",
            "MAX_PIN_ATTEMPTS": "Max PIN attempts before lockout (default: 3)",
            "TELEPHONY_WEBHOOK_SECRET": "Свой секрет в URL вебхука Vapi/Twilio (?secret=...) — без него вебхук отвечает кому угодно",
        },
        "estimated_cost": {
            "monthly_base": "$1-5 USD",
            "per_minute": "~$0.02 USD",
            "free_tier_minutes": 1000,
            "trial_credit": "$15 (Twilio new accounts)"
        }
    }


@router.post("/test-pin-hash")
async def test_pin_hash(request: Request, _=Depends(auth)):
    """
    Utility endpoint to generate PIN hash for .env configuration
    
    Usage: POST /api/call/test-pin-hash with JSON body {"pin_code": "44435"}
    """
    data = await request.json()
    pin_code = data.get("pin_code", "")
    
    if not pin_code:
        raise HTTPException(status_code=400, detail="pin_code required in JSON body")
    
    pin_hash = telephony_client.generate_pin_hash(pin_code)
    return {
        "pin_code": pin_code,
        "sha256_hash": pin_hash,
        "env_line": f"CALL_PIN_HASH={pin_hash}"
    }
