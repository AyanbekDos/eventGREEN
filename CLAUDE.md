# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EventGREEN Bot is a Telegram bot that manages personal client databases with events. It processes VCF files using AI to filter events (birthdays, weddings, anniversaries) and creates personalized Google Sheets tables with notifications.

## Core Architecture

The system follows a three-flow architecture based on `prd.md`:

1. **Flow 1 (VCF Import)**: User uploads VCF → AI processes contacts → Creates personal Google Sheets → Categorizes into "Ideal Clients" (with dates) and "Potential Clients" (without dates)
2. **Flow 2 (Daily CRON)**: Daily notifications at 8:00 AM for events happening today
3. **Flow 3 (Menu Logic)**: Access control based on user status (trial/pro/expired)

### Central Data Store
- **Master Table**: Single Google Sheet with columns: `telegram_id`, `username`, `sheet_url`, `status`, `expires_at`
- **Client Template**: Two-sheet template copied for each user:
  - "✅ Идеальные клиенты" (with event dates)
  - "💡 Потенциальные клиенты" (without dates)

## Key Components

### VCF Processing Pipeline
- `vcf_normalizer.py`: Parses VCF files and extracts text fields with digit detection
- `ai_event_filter.py`: Uses Gemini AI to classify contacts into ideal/potential categories
- `src/vcf_processor.py`: Orchestrates the complete VCF processing workflow

### Google Sheets Integration
- `google_sheets_manager.py`: Manages master table and client sheet operations
- **Important**: Service Accounts cannot create files in personal Drive - requires Shared Drive setup
- **Template System**: Copies client template for each new user

### Telegram Bot
- `src/telegram_bot.py`: Main bot implementation with all commands and handlers
- Supports VCF file uploads, menu navigation, and access control
- Integrates with VCF processor for seamless user experience

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Environment configuration
cp .env.example .env  # Configure required variables
```

### Running the Application
```bash
# Test all components
python main.py test

# Run Telegram bot
python main.py bot

# Manual CRON execution
python main.py cron

# Test VCF processing with real file
python main.py vcf
```

### Testing
```bash
# Interactive test runner
python run_tests.py

# Quick tests
python run_tests.py --type quick

# Demo with real VCF
python run_tests.py --demo-vcf
```

### Cloudflare Workers Deployment
```bash
npm install -g wrangler
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put MASTER_SHEET_ID
wrangler secret put GEMINI_API_KEY
wrangler deploy
```

## Critical Configuration

### Required Environment Variables
- `TELEGRAM_BOT_TOKEN`: Bot token from @BotFather
- `MASTER_SHEET_URL`: Google Sheets master table URL
- `GEMINI_API_KEY`: Google AI API key
- `CLIENT_TEMPLATE_ID`: Template sheet ID for copying

### Service Account Setup
- Place `service.json` in project root
- Service Account must have access to master Google Sheet
- **Important**: For automatic table creation, configure Shared Drive due to Service Account limitations

### Google Sheets Constraints
- Service Accounts cannot create files in personal Drive (storage quota limitations)
- Solution: Use Shared Drive or manual template creation
- Master table must be manually shared with Service Account email

## AI Processing Details

### VCF Text Extraction
- Extracts all text fields from VCard entries
- Detects digits in multiple languages (Russian, Kazakh, English, Arabic)
- Creates `combined_text` for AI analysis
- Filters contacts with phone numbers only

### Gemini AI Integration
- Processes contacts in batches of 15 to avoid token limits
- Identifies events using sophisticated prompt engineering
- Handles typos in month names (e.g., "сенятбрь" → "Сентябрь")
- Returns structured data with event classification

### Event Classification Rules
- **Ideal Clients**: Have specific dates (day + month)
- **Potential Clients**: Have event keywords without specific dates
- **Output Format**: JSON with `name`, `phone`, `event_type`, `event_date`, `note`

## Data Flow Patterns

### User Registration Flow
1. Check if `telegram_id` exists in Master Table
2. If new user: Copy client template → Add to Master Table → Set trial period (30 days)
3. Process VCF through AI pipeline
4. Populate user's personal sheets with categorized contacts

### Daily Notification Flow
1. Query Master Table for active users (trial/pro status)
2. For each user: Read their "Ideal Clients" sheet
3. Filter events where `event_date` matches today
4. Send formatted Telegram message with today's events

### Access Control Logic
- **Trial/Pro**: Full access to all features
- **Expired**: Limited access, shows count of potential clients with upgrade prompt
- Admin contact: @aianback

## Performance Considerations

- VCF files can be 500+ contacts (handle large datasets)
- AI processing uses batching and async patterns
- Implements adaptive optimization based on system resources
- File processing includes progress tracking and error handling

## Error Handling Patterns

- All major operations return structured results with success/error states
- Comprehensive logging using loguru with rotation and compression
- Health checks for all components before bot startup
- Graceful degradation for non-critical failures

## Russian Language Context

- All user-facing messages in Russian
- Supports Cyrillic text in VCF processing
- Month name typo detection for Russian month names
- Date formats accommodate Russian conventions