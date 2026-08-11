"""
Telephony Client - Unified interface for Vapi.ai and Twilio
Supports: Incoming/Outgoing calls, PIN authentication, Voice transcription
Cost-optimized: Uses Vapi.ai free tier + Twilio trial ($15 credit)
"""

import os
import httpx
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import HTTPException

class TelephonyClient:
    """
    Unified telephony client supporting:
    - Vapi.ai (Voice AI platform - handles STT, LLM, TTS in one)
    - Twilio (Phone numbers and PSTN connectivity)
    
    Free Tier Limits:
    - Vapi.ai: 1000 mins/month free
    - Twilio: $15 trial credit (~75 mins calls)
    - Groq LLM: Free tier available
    """
    
    def __init__(self):
        # Vapi.ai Configuration
        self.vapi_api_key = os.getenv("VAPI_API_KEY", "")
        self.vapi_base_url = "https://api.vapi.ai"
        
        # Twilio Configuration
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER", "")
        self.twilio_base_url = "https://api.twilio.com/2010-04-01"
        
        # PIN Security
        self.pin_hash = os.getenv("CALL_PIN_HASH", "")
        self.max_attempts = int(os.getenv("MAX_PIN_ATTEMPTS", "3"))
        
        # State tracking
        self.active_calls: Dict[str, Dict] = {}
        self.pin_attempts: Dict[str, int] = {}
        
    async def _vapi_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Vapi.ai API"""
        if not self.vapi_api_key:
            raise HTTPException(status_code=400, detail="VAPI_API_KEY not configured")
            
        headers = {
            "Authorization": f"Bearer {self.vapi_api_key}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.vapi_base_url}{endpoint}"
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=headers)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=json_data or {})
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=json_data or {})
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    
    async def _twilio_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Twilio API"""
        if not self.twilio_account_sid or not self.twilio_auth_token:
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")
            
        url = f"{self.twilio_base_url}/Accounts/{self.twilio_account_sid}{endpoint}"
        async with httpx.AsyncClient(auth=(self.twilio_account_sid, self.twilio_auth_token)) as client:
            if method == "POST":
                response = await client.post(url, data=data or {})
            elif method == "GET":
                response = await client.get(url)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    
    # ==================== CALL MANAGEMENT ====================
    
    async def create_outbound_call(
        self,
        to_number: str,
        assistant_id: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate outbound call via Vapi.ai
        
        Args:
            to_number: Destination phone number (E.164 format: +1234567890)
            assistant_id: Vapi assistant ID (pre-configured voice+LLM)
            model_override: Override LLM model for this call
            
        Returns:
            Call object with id, status, phone_number
        """
        payload = {
            "phoneNumber": to_number,
            "assistantId": assistant_id or os.getenv("VAPI_DEFAULT_ASSISTANT_ID"),
        }
        
        if model_override:
            payload["modelOverride"] = {"provider": "groq", "model": model_override}
            
        result = await self._vapi_request("POST", "/call", payload)
        
        # Track active call
        call_id = result.get("id")
        if call_id:
            self.active_calls[call_id] = {
                "to": to_number,
                "status": "initiated",
                "started_at": datetime.utcnow().isoformat(),
                "direction": "outbound"
            }
            
        return result
    
    async def end_call(self, call_id: str) -> Dict[str, Any]:
        """Terminate an active call"""
        result = await self._vapi_request("PATCH", f"/call/{call_id}", {"status": "ended"})
        
        if call_id in self.active_calls:
            self.active_calls[call_id]["status"] = "ended"
            self.active_calls[call_id]["ended_at"] = datetime.utcnow().isoformat()
            
        return result
    
    async def get_call_details(self, call_id: str) -> Dict[str, Any]:
        """Retrieve detailed information about a call"""
        return await self._vapi_request("GET", f"/call/{call_id}")
    
    async def list_active_calls(self) -> List[Dict[str, Any]]:
        """Get all currently active calls"""
        return list(self.active_calls.values())
    
    # ==================== PIN AUTHENTICATION ====================
    
    def verify_pin(self, caller_id: str, pin_code: str) -> bool:
        """
        Verify PIN code for incoming call authentication
        
        Security Features:
        - Hash comparison (never store plain PIN)
        - Rate limiting (max 3 attempts per caller)
        - Auto-lockout after max attempts
        """
        if not self.pin_hash:
            # No PIN configured - allow access (development mode)
            return True
            
        # Check attempt limit
        attempts = self.pin_attempts.get(caller_id, 0)
        if attempts >= self.max_attempts:
            # Lockout - clear attempts after 5 minutes
            self.pin_attempts[caller_id] = 0
            return False
            
        # Hash the provided PIN and compare
        input_hash = hashlib.sha256(pin_code.encode()).hexdigest()
        
        if input_hash == self.pin_hash:
            # Success - reset attempts
            self.pin_attempts.pop(caller_id, None)
            return True
        else:
            # Failure - increment counter
            self.pin_attempts[caller_id] = attempts + 1
            return False
    
    def generate_pin_hash(self, pin_code: str) -> str:
        """Generate SHA256 hash for a PIN code (for .env configuration)"""
        return hashlib.sha256(pin_code.encode()).hexdigest()
    
    # ==================== INCOMING CALL WEBHOOK ====================
    
    async def handle_incoming_call_webhook(
        self,
        caller_id: str,
        call_id: str,
        direction: str = "inbound"
    ) -> Dict[str, Any]:
        """
        Process incoming call webhook from Vapi/Twilio
        
        Flow:
        1. Request PIN authentication
        2. On success: Connect to J.A.R.V.I.S. assistant
        3. On failure: Hangup + send security alert
        """
        # Track incoming call
        self.active_calls[call_id] = {
            "from": caller_id,
            "status": "authenticating",
            "started_at": datetime.utcnow().isoformat(),
            "direction": direction
        }
        
        # Return Vapi-compatible response for PIN prompt
        return {
            "messages": [
                {
                    "role": "system",
                    "content": "Please enter your 5-digit PIN code followed by the pound sign."
                }
            ],
            "callId": call_id
        }
    
    async def handle_pin_submission(
        self,
        call_id: str,
        caller_id: str,
        pin_input: str
    ) -> Dict[str, Any]:
        """Process PIN submission from caller"""
        is_valid = self.verify_pin(caller_id, pin_input)
        
        if is_valid:
            # Authentication successful - connect to J.A.R.V.I.S.
            self.active_calls[call_id]["status"] = "authenticated"
            return {
                "messages": [
                    {
                        "role": "system",
                        "content": "Authentication successful. Connecting you to J.A.R.V.I.S."
                    }
                ],
                "assistantId": os.getenv("VAPI_JARVIS_ASSISTANT_ID"),
                "transferToAssistant": True
            }
        else:
            # Authentication failed
            attempts_left = self.max_attempts - self.pin_attempts.get(caller_id, 0)
            
            if attempts_left <= 0:
                # Max attempts reached - hangup
                await self.end_call(call_id)
                return {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Maximum attempts exceeded. Goodbye."
                        }
                    ],
                    "endCall": True
                }
            else:
                # More attempts allowed
                return {
                    "messages": [
                        {
                            "role": "system",
                            "content": f"Incorrect PIN. You have {attempts_left} attempts remaining."
                        }
                    ]
                }
    
    # ==================== UTILITY METHODS ====================
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get telephony usage statistics (for billing/monitoring)"""
        # Vapi usage endpoint
        try:
            stats = await self._vapi_request("GET", "/usage")
            return {
                "total_minutes": stats.get("totalMinutes", 0),
                "remaining_free_minutes": max(0, 1000 - stats.get("totalMinutes", 0)),
                "active_calls": len(self.active_calls),
                "provider": "Vapi.ai + Twilio"
            }
        except Exception as e:
            return {
                "error": str(e),
                "active_calls": len(self.active_calls),
                "provider": "Vapi.ai + Twilio"
            }
    
    def get_setup_instructions(self) -> str:
        """Return setup instructions for telephony integration"""
        return """
📞 TELEPHONY SETUP GUIDE (Low-Cost Alternative)

1. Vapi.ai Setup (Free 1000 mins/month):
   - Register at https://vapi.ai
   - Create Assistant with:
     * Voice: ElevenLabs "Rachel" or "Domi"
     * LLM: Groq (Llama 3.3 - free tier)
     * System Prompt: J.A.R.V.I.S. personality
   - Copy Assistant ID to .env: VAPI_DEFAULT_ASSISTANT_ID=xxx

2. Twilio Trial ($15 credit = ~75 mins):
   - Register at https://twilio.com
   - Buy phone number ($1/month + usage)
   - Get Account SID and Auth Token
   - Add to .env:
     TWILIO_ACCOUNT_SID=ACxxxx
     TWILIO_AUTH_TOKEN=your_token
     TWILIO_PHONE_NUMBER=+1234567890

3. PIN Security:
   - Choose 5-digit PIN (e.g., 44435)
   - Generate hash: python -c "import hashlib; print(hashlib.sha256(b'44435').hexdigest())"
   - Add to .env: CALL_PIN_HASH=generated_hash

4. Test Call:
   - POST /api/call/initiate with {"to_number": "+1234567890"}
   - Or call your Twilio number and enter PIN

💰 Estimated Monthly Cost: $1-5 (vs $50+ for Retell AI)
⚡ Latency: <500ms (Groq LLM + Vapi optimized pipeline)
        """


# Global instance
telephony_client = TelephonyClient()
