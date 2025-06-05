# Streak Scoring Microservice

A FastAPI-based microservice that tracks and validates user engagement streaks across various action types (logins, quiz completions, help post submissions). Features AI-powered validation and high configurability.

## 🚀 Quick Start

```bash
# Clone the repository
git clone <your-repository-url>
cd streak_service_project

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive API documentation.

## ✨ Key Features

- 📊 **Multi-Action Streak Tracking**
  - Tracks independent streaks for different action types
  - Supports login, quiz completion, and help post submissions
  - Configurable validation rules per action type

- 🤖 **AI-Powered Validation**
  - TF-IDF + Logistic Regression model for content validation
  - Automatic quality assessment of help posts
  - Easy model retraining and versioning

- ⚙️ **Highly Configurable**
  - Customizable streak tiers (bronze, silver, gold)
  - Configurable grace periods
  - Adjustable validation rules
  - Version-controlled AI models

- 🛠️ **Developer Friendly**
  - OpenAPI/Swagger documentation
  - Comprehensive test suite
  - Docker support
  - Health check endpoints

## 📁 Project Structure

```
streak_service_project/
├── app/                    # Main application code
│   ├── ai/                # AI model training and validation
│   ├── core/              # Core components and configuration
│   ├── models/            # Pydantic models
│   ├── services/          # Business logic
│   └── main.py           # FastAPI application
├── data/                  # Data files and trained models
├── tests/                 # Test suite
├── config.json           # Service configuration
├── Dockerfile            # Docker configuration
└── requirements.txt      # Python dependencies
```

## 🔧 Configuration

The service is configured via `config.json`. Key configuration options:

```json
{
  "activity_types": {
    "login": { "enabled": true },
    "quiz": {
      "enabled": true,
      "min_score": 70
    },
    "help_post": {
      "enabled": true,
      "min_word_count": 50,
      "ai_validation_enabled": true
    }
  },
  "streak_tiers": [
    { "name": "bronze", "min_streak": 3 },
    { "name": "silver", "min_streak": 7 },
    { "name": "gold", "min_streak": 14 }
  ],
  "grace_period_hours": 24
}
```

## 📡 API Endpoints

### Update Streaks
```http
POST /streaks/update
Content-Type: application/json

{
  "user_id": "user123",
  "date_utc": "2024-03-20T10:00:00Z",
  "actions": [
    {
      "type": "quiz",
      "metadata": {
        "quiz_id": "quiz1",
        "score": 85,
        "time_taken_sec": 300
      }
    }
  ]
}
```

### Health Check
```http
GET /health
Response: {"status": "ok"}
```

### Version Info
```http
GET /version
Response: {
  "service_name": "Streak Scoring Microservice",
  "service_api_version": "1.0.0",
  "ai_model_versions": {
    "help_post_classifier": "1.0.0"
  }
}
```

## 🐳 Docker Deployment

```bash
# Build the image
docker build -t streak-scorer-app .

# Run the container
docker run -p 8000:8000 -d --name my-streak-app streak-scorer-app
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest -v
```

## 📝 Notes

- The AI model requires training data in `data/help_post_training_data.csv`
- Minimum 300-500 diverse examples recommended for good model performance
- NLTK stopwords are automatically downloaded on first run
- Service uses UTC timestamps for all date/time operations

## 🔐 Security Considerations

- All API endpoints should be secured in production
- API keys or authentication should be implemented
- Sensitive configuration should be managed via environment variables
- Regular security updates of dependencies recommended

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

[Your License Here]
