# Transcription Frontend Application

A full-stack application for audio transcription with a Vue.js frontend and FastAPI backend.

## Project Overview

This application allows users to upload audio files, generate transcriptions, and view/manage the resulting transcriptions. It uses Whisper AI model for transcription and provides a user-friendly interface for managing transcriptions.

## Architecture

The project consists of two main components:

- **Frontend**: A Vue.js application built with Vite
- **Backend**: A Python FastAPI application that handles audio processing and transcription

Both components are containerized using Docker and can be deployed using docker-compose.

## Features

- User authentication (JWT-based)
- Audio file upload
- Audio transcription using Whisper AI model
- Waveform visualization of audio files
- Transcription management (view, list, delete)
- Real-time transcription progress reporting

## Tech Stack

### Frontend

- Vue.js 3 with Composition API
- Vuetify for UI components
- Pinia for state management
- Axios for API requests
- WaveSurfer.js for audio visualization
- Vue Router for navigation
- Vue3-Toastify for notifications

### Backend

- FastAPI as the web framework
- OpenAI Whisper for speech-to-text transcription
- TinyDB for lightweight data storage
- JWT for authentication
- bcrypt for password hashing

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js and pnpm (for local development)
- Python 3.11+ (for local backend development)

### Running with Docker Compose

1. Clone the repository
2. Set up environment variables:
   - Create `.env` files in both frontend and backend directories
3. Start the application:

```bash
docker-compose up -d
```

### Local Development

#### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Environment Variables

### Frontend

- `VITE_API_URL`: URL for the backend API

### Backend

- `SECRET`: Secret key for JWT generation
- `TRANSCRIPT_USER`: Username for authentication
- `TRANSCRIPT_PASSWORD`: Password for authentication
- `HUGGINGFACE_API_URL`: (Optional) URL for HuggingFace API
- `HUGGINGFACE_TOKEN`: (Optional) Token for HuggingFace API

## Deployment

The application is configured to work with Nginx and Let's Encrypt for HTTPS. The docker-compose file contains the necessary configuration for deployment.

## API Endpoints

- `/token`: Authenticate and receive JWT token
- `/status`: Check application status
- `/transcribe`: Upload audio for transcription
- `/transcriptions`: Get all transcriptions
- `/transcriptions/{id}`: Get a specific transcription
- `/audio/{id}`: Get audio file for a transcription
- `/transcriptions/{id}`: Delete a transcription

## License

[Insert license information here]

## Contributors

- Fabian Abraham (mail@fabraham.dev)
