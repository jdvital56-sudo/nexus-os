import os
import json
import datetime
from typing import Optional, List, Dict, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

class GoogleCalendarClient:
    def __init__(self):
        self.service = None
        self.creds = None
        self._initialized = False
        
        # Check if credentials file exists
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"⚠️ WARNING: {CREDENTIALS_FILE} not found. Google Calendar features disabled.")
            print("Please download credentials.json from Google Cloud Console and place it in the project root.")

    def authenticate(self) -> bool:
        """OAuth 2.0 авторизация"""
        if not os.path.exists(CREDENTIALS_FILE):
            return False
            
        try:
            if os.path.exists(TOKEN_FILE):
                self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            
            # If there are no (valid) credentials available, let the user log in.
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    self.creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(TOKEN_FILE, 'w') as token:
                    token.write(self.creds.to_json())
            
            self.service = build('calendar', 'v3', credentials=self.creds)
            self._initialized = True
            return True
            
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False

    async def create_event(
        self, 
        summary: str, 
        start_time: str, 
        end_time: str, 
        description: str = "",
        attendees: Optional[List[str]] = None,
        timezone: str = "Europe/Moscow"
    ) -> Dict[str, Any]:
        """Создание события в календаре"""
        if not self._initialized and not self.authenticate():
            return {"error": "Google Calendar not authenticated"}
        
        try:
            event = {
                'summary': summary,
                'description': description,
                'start': {'dateTime': start_time, 'timeZone': timezone},
                'end': {'dateTime': end_time, 'timeZone': timezone},
            }
            
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            created_event = self.service.events().insert(
                calendarId='primary', 
                body=event,
                sendUpdates='all'  # Send email notifications
            ).execute()
            
            return {
                "success": True,
                "event_id": created_event.get('id'),
                "html_link": created_event.get('htmlLink'),
                "summary": created_event.get('summary')
            }
            
        except HttpError as error:
            return {"error": f"Google Calendar API error: {str(error)}"}

    async def list_events(
        self, 
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None
    ) -> Dict[str, Any]:
        """Получение списка событий"""
        if not self._initialized and not self.authenticate():
            return {"error": "Google Calendar not authenticated"}
        
        try:
            now = time_min or datetime.datetime.utcnow().isoformat() + 'Z'
            
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Format events for easier consumption
            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                formatted_events.append({
                    'id': event.get('id'),
                    'summary': event.get('summary'),
                    'description': event.get('description', ''),
                    'start': start,
                    'end': end,
                    'location': event.get('location', ''),
                    'attendees': [a.get('email') for a in event.get('attendees', [])]
                })
            
            return {"events": formatted_events, "count": len(formatted_events)}
            
        except HttpError as error:
            return {"error": f"Google Calendar API error: {str(error)}"}

    async def delete_event(self, event_id: str) -> Dict[str, Any]:
        """Удаление события"""
        if not self._initialized and not self.authenticate():
            return {"error": "Google Calendar not authenticated"}
        
        try:
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id,
                sendUpdates='all'
            ).execute()
            
            return {"success": True, "message": f"Event {event_id} deleted"}
            
        except HttpError as error:
            return {"error": f"Google Calendar API error: {str(error)}"}

    async def update_event(
        self, 
        event_id: str, 
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """Обновление события"""
        if not self._initialized and not self.authenticate():
            return {"error": "Google Calendar not authenticated"}
        
        try:
            # Get existing event
            event = self.service.events().get(
                calendarId='primary', 
                eventId=event_id
            ).execute()
            
            # Update fields
            if summary:
                event['summary'] = summary
            if description:
                event['description'] = description
            if start_time:
                event['start']['dateTime'] = start_time
            if end_time:
                event['end']['dateTime'] = end_time
            
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendUpdates='all'
            ).execute()
            
            return {
                "success": True,
                "event_id": updated_event.get('id'),
                "html_link": updated_event.get('htmlLink')
            }
            
        except HttpError as error:
            return {"error": f"Google Calendar API error: {str(error)}"}

# Singleton instance
google_calendar_client = GoogleCalendarClient()
