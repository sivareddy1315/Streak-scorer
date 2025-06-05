# Start with an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NLTK_DATA=/usr/share/nltk_data

# Set the working directory in the container
WORKDIR /app

# Install build tools needed for packages like pandas, numpy, scikit-learn, etc.
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker layer caching
COPY requirements.txt ./

# Install Python dependencies (including nltk)
RUN pip install --no-cache-dir --compile -r requirements.txt

# Now that nltk is installed, create directory for NLTK data and download stopwords
RUN mkdir -p /usr/share/nltk_data && \
    python -m nltk.downloader -d /usr/share/nltk_data stopwords && \
    # Optional: Verify download - Use double quotes for "english" inside the Python code
    python -c "from nltk.corpus import stopwords; print(f'NLTK Stopwords sample: {stopwords.words(\"english\")[0]}')"

# Copy the entire application into the container
COPY . .

# Make port 8000 available
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]