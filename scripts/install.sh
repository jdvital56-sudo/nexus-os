# 🚀 HERMES INSTALLATION SCRIPT
# Quick setup for NEXSYS Hermes Agent

#!/bin/bash

echo "🔧 Starting NEXSYS Hermes Installation..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is required but not installed.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo -e "${GREEN}✅ Python $PYTHON_VERSION detected${NC}"

# Create virtual environment (optional but recommended)
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing Python dependencies..."
pip install -r backend/requirements.txt --quiet
pip install python-telegram-bot APScheduler google-auth google-auth-oauthlib google-api-python-client --quiet
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Copy .env.example to .env
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo -e "${YELLOW}⚠️ Please edit .env and add your API keys${NC}"
else
    echo -e "${GREEN}✅ .env file already exists${NC}"
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p artifacts
mkdir -p ~/.nexsys
mkdir -p documents/hermes
echo -e "${GREEN}✅ Directories created${NC}"

# Instructions for Telegram Bot setup
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📱 TELEGRAM BOT SETUP INSTRUCTIONS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Open Telegram and search for @BotFather"
echo "2. Send /newbot command"
echo "3. Choose a name for your bot (e.g., 'My Hermes Assistant')"
echo "4. Choose a username (must end with 'bot', e.g., 'my_hermes_bot')"
echo "5. Copy the API token provided"
echo ""
echo "6. Search for @UserInfobot to get your Telegram User ID"
echo ""
echo "7. Edit .env file and add:"
echo "   TELEGRAM_BOT_TOKEN=your_token_here"
echo "   TELEGRAM_ALLOWED_USER_ID=your_user_id_here"
echo ""

# Instructions for API Keys
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔑 API KEYS TO CONFIGURE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. DeepSeek (Recommended for cost-effective AI):"
echo "   → https://platform.deepseek.com/api_keys"
echo ""
echo "2. Google Gemini (Required for audio transcription):"
echo "   → https://aistudio.google.com/app/apikey"
echo ""
echo "3. Apollo.io (For B2B lead generation):"
echo "   → https://www.apollo.io/settings/api-keys"
echo ""
echo "4. Anthropic Claude (Optional, for complex reasoning):"
echo "   → https://console.anthropic.com/settings/keys"
echo ""
echo "5. OpenAI (Optional, general purpose):"
echo "   → https://platform.openai.com/api-keys"
echo ""

# Google Calendar OAuth Setup
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📅 GOOGLE CALENDAR SETUP (Optional)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Go to https://console.cloud.google.com/"
echo "2. Create a new project"
echo "3. Enable Google Calendar API and Gmail API"
echo "4. Create OAuth 2.0 credentials (Desktop app)"
echo "5. Download credentials.json and place in project root"
echo ""

# Final instructions
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ INSTALLATION COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Run: python hermes/bot.py"
echo "3. Send /start to your Telegram bot"
echo ""
echo "To start Dream Cadence (night analytics):"
echo "  The system will automatically run at 3 AM"
echo "  Morning brief will be sent to your Telegram"
echo ""
echo -e "${GREEN}🚀 Ready to launch Hermes!${NC}"
echo ""
