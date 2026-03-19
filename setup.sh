#!/bin/bash

# RFP and Grants Scraping System - Setup Script
# This script sets up the complete environment

echo "=========================================="
echo "RFP and Grants Scraping System Setup"
echo "=========================================="
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

if [ $? -ne 0 ]; then
    echo "❌ Failed to create virtual environment"
    exit 1
fi

echo "✅ Virtual environment created"
echo ""

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "✅ Dependencies installed"
echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env file with your Supabase credentials"
    echo "   Run: nano .env"
    echo ""
else
    echo "✅ .env file already exists"
    echo ""
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs downloads
echo "✅ Directories created"
echo ""

# Test database connection
echo "🔍 Testing database connection..."
python3 -c "
from database.db import db
try:
    db.create_tables()
    print('✅ Database connection successful')
    print('✅ Tables created/verified')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    print('⚠️  Please check your .env configuration')
"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials: nano .env"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Run the scraper: python main.py"
echo ""
echo "For automation, set up a cron job:"
echo "  crontab -e"
echo "  Add: 0 2 * * * cd $(pwd) && source venv/bin/activate && python main.py"
echo ""
echo "=========================================="
