# Streak Scoring Microservice

A FastAPI-based microservice designed to track and validate user engagement streaks across various action types such as logins, quiz completions, and help post submissions. It features AI-powered validation for content-based streaks and is highly configurable.

## Table of Contents
- [Features](#features)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup and Local Development](#setup-and-local-development)
- [Configuration](#configuration)
- [Running the AI Model Trainer](#running-the-ai-model-trainer)
- [API Endpoints](#api-endpoints)
- [Running Tests](#running-tests)
- [Docker Deployment](#docker-deployment)
- [Notes and Limitations](#notes-and-limitations)

## Features

*   Tracks independent streaks per user for multiple action types (e.g., `login`, `quiz`, `help_post`).
*   Utilizes a TF-IDF + Logistic Regression model for AI-based validation of `help_post` content.
*   Configurable via `config.json` for:
    *   Activity types and their specific validation rules (e.g., min word count, min quiz score).
    *   Streak progression tiers (e.g., none, bronze, silver, gold).
    *   Grace period logic for streak continuation.
    *   AI model versions.
*   Built with Python, FastAPI, and Uvicorn.
*   Provides `/health` and `/version` status endpoints.
*   Automatic OpenAPI (Swagger UI at `/docs`) and ReDoc (at `/redoc`) API documentation.
*   Containerized using Docker.

## Project Structure
streak_service_project/
├── app/ # Main application source code
│ ├── ai/ # AI model training and validation logic
│ │ ├── init.py
│ │ └── validator.py # ContentValidator class
│ │ └── trainer.py # Script to train the AI model
│ ├── core/ # Core components like configuration loading
│ │ ├── init.py
│ │ └── config.py # AppConfig class
│ ├── models/ # Pydantic models for API request/response
│ │ ├── init.py
│ │ └── streaks_models.py
│ ├── services/ # Business logic for streak calculations
│ │ ├── init.py
│ │ └── streak_logic.py # StreakCalculatorService class
│ └── main.py # FastAPI application, endpoints
├── data/ # Data files
│ ├── help_post_training_data.csv # Training data for AI model
│ └── trained_models/ # Directory for saved .pkl model files
├── tests/ # Automated tests
│ ├── init.py
│ └── test_api.py # Pytest API tests
├── config.json # Service configuration file
├── Dockerfile # Docker image definition
├── requirements.txt # Python dependencies
├── .dockerignore # Specifies intentionally untracked files that Docker should ignore
├── .gitignore # Specifies intentionally untracked files that Git should ignore
└── README.md # This file

## Prerequisites

*   Python 3.9+
*   Docker (for containerization)
*   `pip` (Python package installer)
*   A terminal or command prompt.

## Setup and Local Development

1.  **Clone the Repository (if applicable)**
    ```bash
    # git clone <your-repository-url>
    cd streak_service_project
    ```

2.  **Create and Activate a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On macOS/Linux
    # venv\Scripts\activate  # On Windows
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    This installs FastAPI, Uvicorn, scikit-learn, pandas, nltk, pytest, httpx, etc.

4.  **NLTK Stopwords Download:**
    The `trainer.py` and `validator.py` scripts will attempt to download the NLTK `stopwords` corpus on their first run if not found. This is also handled in the `Dockerfile`.

5.  **Prepare Training Data for AI Model:**
    *   The AI model for `help_post` validation requires training data. Ensure `data/help_post_training_data.csv` is present.
    *   **This file is crucial.** It must have a header row: `content,word_count,char_count,contains_code,question_count,sentence_count,label`.
    *   The `content` and `label` (1 for good/valid, 0 for bad/invalid) columns are used for training. The other columns are for your reference or potential future use.
    *   **You need to curate this file with many diverse, high-quality examples (300-500+ recommended) for the AI to perform well on real-life inputs.**

6.  **Train the AI Model:**
    If you have updated `data/help_post_training_data.csv`, or if the trained model file (e.g., `data/trained_models/help_post_classifier_v1.0.0.pkl`) doesn't exist:
    ```bash
    python app/ai/trainer.py
    ```
    This will create/update the `.pkl` model file. Ensure the version specified in `config.json` under `model_versions.help_post_classifier` matches the version used in the trainer script (currently hardcoded to "1.0.0" in `trainer.py`).

7.  **Configure the Service:**
    *   Review and customize `config.json`. This file controls:
        *   Enabled activity types (`login`, `quiz`, `help_post`).
        *   Validators for each type (e.g., `min_word_count` for `help_post`, `min_score` for `quiz`, `ai_validation_enabled` for `help_post`).
        *   Streak tier definitions (`name`, `min_streak`).
        *   Grace period duration (`grace_period_hours`).
        *   AI model version to load.

8.  **Run the FastAPI Application Locally:**
    ```bash
    uvicorn app.main:app --reload --port 8000 --log-level info
    ```
    *   `--reload`: Uvicorn will automatically restart when code changes are detected (for development).
    *   `--port 8000`: Runs the service on port 8000.
    *   `--log-level info`: Sets the logging level. Use `debug` for more verbose output.
    *   The service will be available at `http://127.0.0.1:8000`.
    *   Interactive API documentation (Swagger UI): `http://127.0.0.1:8000/docs`.
    *   Alternative API documentation (ReDoc): `http://127.0.0.1:8000/redoc`.

## API Endpoints

*   **`GET /`**
    *   Description: Displays a simple HTML welcome page with links to documentation and other key endpoints.
    *   Response: HTML content.

*   **`POST /streaks/update`**
    *   Description: Updates user streaks based on a list of actions performed by the user. Validates actions based on configured rules, including AI validation for `help_post` content.
    *   Request Body: See `StreakUpdateRequest` in `app/models/streaks_models.py` or `/docs`.
        ```json
        {
          "user_id": "string",
          "date_utc": "datetime (ISO 8601 string)",
          "actions": [
            {
              "type": "string (e.g., login, quiz, help_post)",
              "metadata": {
                // "quiz": {"quiz_id": "string", "score": int, "time_taken_sec": int}
                // "help_post": {"content": "string", "word_count": int, "contains_code": bool}
                // "login": {}
              }
            }
          ]
        }
        ```
    *   Response Body: See `StreakUpdateResponse` in `app/models/streaks_models.py` or `/docs`. Includes current streak details for each processed action type.

*   **`GET /health`**
    *   Description: Standard health check endpoint.
    *   Response: `{"status": "ok"}`

*   **`GET /version`**
    *   Description: Provides version information for the service and loaded AI models.
    *   Response Example:
      ```json
      {
        "service_name": "Streak Scoring Microservice",
        "service_api_version": "1.0.0",
        "ai_model_versions": {
          "help_post_classifier": "1.0.0"
        }
      }
      ```

## Running Tests

The project uses `pytest` for automated testing. Tests are located in the `tests/` directory.

1.  Ensure all dependencies, including `pytest` and `httpx`, are installed (from `requirements.txt`).
2.  From the project root directory (`streak_service_project`), run:
    ```bash
    pytest
    ```
    or for more verbose output:
    ```bash
    pytest -v
    ```
    To run a specific test file or test function:
    ```bash
    pytest tests/test_api.py -k "test_initial_valid_actions"
    ```

## Docker Deployment

1.  **Build the Docker Image:**
    From the project root directory:
    ```bash
    docker build -t streak-scorer-app .
    ```
    *(You can change `streak-scorer-app` to your preferred image name, e.g., `streak-scorer` as in the PDF).*

2.  **Run the Docker Container:**
    ```bash
    docker run -p 8000:8000 -d --name my-streak-app streak-scorer-app
    ```
    *   `-p 8000:8000`: Maps port 8000 of the container to port 8000 on the host.
    *   `-d`: Runs the container in detached (background) mode.
    *   `--name my-streak-app`: Assigns a name to the running container for easier management.
    *   The service will be accessible at `http://localhost:8000`.
    *   The `config.json` file and the trained AI model(s) are copied into the Docker image during the build process.

3.  **View Container Logs:**
    ```bash
    docker logs my-streak-app
    ```
    To follow logs in real-time:
    ```bash
    docker logs -f my-streak-app
    ```

4.  **Stop and Remove the Container:**
    ```bash
    docker stop my-streak-app
    docker rm my-streak-app
    ```

## Notes and Limitations

*   **AI Model Performance:** The effectiveness of the `help_post` content validation is highly dependent on the quality, diversity, and size of the training data in `data/help_post_training_data.csv`. Continuous curation and retraining are essential for robust real-world performance.
*   **Persistence:** User streak data is currently stored **in-memory** within the `streak_logic.py` module. This means all streak data will be lost if the service restarts. For a production environment requiring data persistence, this in-memory store should be replaced with a persistent database solution (e.g., Redis for caching/streaks, PostgreSQL for more structured data).
*   **Scalability:** Due to the in-memory data store, the service in its current form cannot be easily scaled horizontally (i.e., running multiple instances behind a load balancer) as each instance would have its own separate streak data. A shared, persistent data store is a prerequisite for horizontal scaling.
*   **Quiz AI Validation:** AI-based validation for `quiz` content is marked as optional in the project requirements and is not implemented. Non-AI validation for quizzes (based on score, time taken) is implemented.# Streak-scorer
