# Streak Scoring Microservice

A FastAPI-based microservice that tracks and validates user engagement streaks across various action types (logins, quiz completions, help post submissions). Features AI-powered validation and high configurability.

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/sivareddy1315/Streak-scorer.git
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

> **Note:**
> All pretrained model and vectorizer `.pkl` files must be present in the `data/trained_models/` directory for the service to function correctly. Ensure these files are included when building or deploying the Docker image.

```json
{
  "service_version": "1.0.0",
  "model_versions": {
    "help_post_classifier": "1.0.0"
  },
  "activity_types": {
    "login": {
      "enabled": true,
      "streak_definition": {
        "unit": "day",
        "value": 1
      }
    },
    "quiz": {
      "enabled": true,
      "streak_definition": {
        "unit": "day",
        "value": 1
      },
      "validators": {
        "min_score": 5,
        "max_time_taken_sec": 600
      }
    },
    "help_post": {
      "enabled": true,
      "streak_definition": {
        "unit": "day",
        "value": 1
      },
      "validators": {
        "ai_validation_enabled": true,
        "min_word_count": 10
      }
    }
  },
  "streak_tiers": [
    {"name": "none", "min_streak": 0},
    {"name": "bronze", "min_streak": 3},
    {"name": "silver", "min_streak": 7},
    {"name": "gold", "min_streak": 14}
  ],
  "daily_reset_hour_utc": 0,
  "next_deadline_buffer_seconds": -1,
  "grace_period_hours": 2
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

## ✨ Acknowledgements

This project was developed with the assistance of modern AI-powered tools to accelerate development and improve code quality.

- **Cursor:** Used as the primary AI-first code editor for code generation, refactoring, and debugging.
- **Google AI Studio:** Utilized for high-level conceptual brainstorming, structuring documentation, and generating the project report.


