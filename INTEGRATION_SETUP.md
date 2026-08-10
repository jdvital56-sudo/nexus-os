# 🚀 NEXSYS Integration Setup Guide

This guide covers the setup for Apollo.io, Google Calendar, and Google Gemini integrations.

## 1. Apollo.io Integration (Contact & Company Search)

### Get API Key
1. Register at [Apollo.io](https://www.apollo.io)
2. Go to **Settings → API Keys**
3. Click **Generate API Key**
4. Copy the key

### Configure
Add to your `.env` file:
```bash
NEXSYS_APOLLO_API_KEY=your_apollo_api_key_here
```

### Test
```python
from backend.services.apollo_client import apollo_client

# Search people
result = await apollo_client.search_people(keywords="tech startups")
print(result)

# Search companies
companies = await apollo_client.search_companies(keywords="artificial intelligence")
print(companies)

# Enrich contact by email
person = await apollo_client.enrich_person(email="founder@startup.com")
print(person)
```

### API Endpoints
- `POST /api/apollo/search` - Search contacts
- `GET /api/apollo/person/{id}` - Get contact details
- `POST /api/apollo/companies` - Search companies
- `POST /api/apollo/enrich` - Enrich data by email

---

## 2. Google Calendar Integration (Event Management)

### Setup OAuth 2.0
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Calendar API**:
   - Go to **APIs & Services → Library**
   - Search "Google Calendar API"
   - Click **Enable**

4. Create OAuth 2.0 Credentials:
   - Go to **APIs & Services → Credentials**
   - Click **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download `credentials.json`

5. Place `credentials.json` in project root:
   ```
   /workspace/credentials.json
   ```

### First-Time Authentication
Run the authentication flow:
```python
from backend.services.google_calendar import google_calendar_client

# This will open browser for OAuth
google_calendar_client.authenticate()
```

A browser window will open. Log in with your Google account and grant permissions. A `token.json` file will be created automatically.

### Test
```python
from backend.services.google_calendar import google_calendar_client

# List events
events = await google_calendar_client.list_events(max_results=5)
print(events)

# Create event
event = await google_calendar_client.create_event(
    summary="Team Meeting",
    start_time="2025-01-20T10:00:00",
    end_time="2025-01-20T11:00:00",
    description="Weekly sync",
    attendees=["team@example.com"]
)
print(event)
```

### API Endpoints
- `POST /api/calendar/events` - Create event
- `GET /api/calendar/events` - List events
- `PUT /api/calendar/events/{id}` - Update event
- `DELETE /api/calendar/events/{id}` - Delete event
- `POST /api/calendar/auth` - Start OAuth flow

---

## 3. Google Gemini Integration (Real LLM Calls)

### Get API Key
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click **Create API Key**
3. Copy the key

### Configure
Add to your `.env` file:
```bash
NEXSYS_GEMINI_API_KEY=your_gemini_api_key_here
NEXSYS_LLM_PROVIDER=gemini
NEXSYS_LLM_MODEL=gemini-2.0-flash
```

### Test
```python
from backend.services.llm import get_llm_service, LLMMessage

llm = get_llm_service()

# Chat
messages = [LLMMessage(role="user", content="Hello!")]
response = await llm.chat(messages)
print(response.content)

# Generate response with context
answer = await llm.generate_response(
    user_message="What is machine learning?",
    context="Explain in simple terms for beginners"
)
print(answer)

# Process audio (requires audio file)
plan = await llm.generate_plan(
    audio_path="recording.mp3",
    prompt="Extract action items from this meeting recording"
)
print(plan)
```

### Supported Models
- `gemini-2.0-flash` - Fast, multimodal (text + audio)
- `gemini-1.5-pro` - Advanced reasoning
- `gemini-1.5-flash` - Balanced performance

---

## Quick Verification Script

Run this to check all integrations:

```bash
cd /workspace
python -c "
from backend.services.apollo_client import apollo_client
from backend.services.google_calendar import google_calendar_client
from backend.services.llm import get_llm_service

print('=== Integration Status ===')
print(f'Apollo API Key: {\"✅ Configured\" if apollo_client.api_key else \"❌ Missing\"}')
print(f'Google Calendar: {\"✅ Ready\" if google_calendar_client._initialized or google_calendar_client.authenticate() else \"❌ Needs credentials.json\"}')
print(f'Gemini API Key: {\"✅ Configured\" if get_llm_service().gemini_api_key else \"❌ Missing\"}')
"
```

---

## Troubleshooting

### Apollo.io
- **Error: 401 Unauthorized** → Check API key is correct
- **Error: 403 Forbidden** → Verify API key has proper permissions
- **Rate limits** → Free tier: 50 requests/day

### Google Calendar
- **credentials.json not found** → Download from Google Cloud Console
- **Token expired** → Delete `token.json` and re-authenticate
- **Scope errors** → Ensure Calendar API is enabled

### Google Gemini
- **Error: API_KEY_INVALID** → Regenerate key at AI Studio
- **Quota exceeded** → Check usage limits in Google Cloud Console
- **Audio processing fails** → Ensure file is valid MP3/WAV format

---

## Next Steps

After configuring all integrations:

1. **Restart the server**:
   ```bash
   python backend/main.py
   ```

2. **Test via API**:
   ```bash
   curl http://localhost:8420/api/apollo/search -X POST -H "Content-Type: application/json" -d '{"keywords": "startups"}'
   ```

3. **Use in Skills**:
   - `apollo-lead-search` - Find leads via Apollo
   - `calendar-schedule-meeting` - Schedule meetings
   - `gemini-audio-transcribe` - Transcribe audio notes

All integrations are now ready for production use! 🎉
