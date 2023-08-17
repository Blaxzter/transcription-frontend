import base64
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
import requests
import uuid
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import FileResponse
from tinydb import TinyDB

from dotenv import load_dotenv
from tinydb import Query

load_dotenv()

app = FastAPI()
origins = [
    "http://localhost",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

file_path = os.path.dirname(__file__)
os.makedirs(os.path.join(file_path, 'audio_files'), exist_ok = True)

SECRET_KEY = os.getenv('SECRET')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 3000

path = os.path.dirname(__file__)
db = TinyDB(os.path.join(path, 'db.json'))
transcript_model = Query()
transcripts = db.table('transcribes')
job_db = db.table('jobs')


def hash_password(pw):
    pwhash = bcrypt.hashpw(pw.encode('utf8'), bcrypt.gensalt())
    return pwhash.decode('utf8')


HUGGINGFACE_API_URL = os.getenv('HUGGINGFACE_API_URL')
HUGGINGFACE_TOKEN = os.getenv('HUGGINGFACE_TOKEN')
USERS = {os.getenv('TRANSCRIPT_USER'): hash_password(os.environ.get("TRANSCRIPT_PASSWORD"))}

headers = {
    "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
    "Content-Type": "application/json",
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl = "token")
last_request: datetime.date = datetime.utcnow()


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


def check_password(pw, hashed_pw):
    expected_hash = hashed_pw.encode('utf8')
    return bcrypt.checkpw(pw.encode('utf8'), expected_hash)


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_user(username: str):
    if username in USERS:
        return {"username": username, "hashed_password": USERS[username]}
    return None


def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes = 15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm = ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code = 401, detail = "Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms = [ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username = username)
    except jwt.PyJWTError:
        raise credentials_exception
    user = get_user(username = token_data.username)
    if user is None:
        raise credentials_exception
    return user


@app.post("/token", response_model = Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code = 401, detail = "Incorrect username or password")
    access_token_expires = timedelta(minutes = ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data = {"sub": form_data.username}, expires_delta = access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/transcribe", dependencies = [Depends(get_current_user)])
async def upload_audio_file(file: UploadFile = File(...)):
    # Rest of the code...
    audio_bytes = await file.read()
    audio_data = base64.b64encode(audio_bytes).decode()

    data_dict = json.dumps(
        {"inputs": [], "audio_data": audio_data, "options": {"task": "transcribe", "language": "<|de|>"}})
    response = requests.post(HUGGINGFACE_API_URL, headers = headers, data = data_dict)

    # store audio file in 'audio_files' under name uuid
    transcript_id = str(uuid.uuid4())
    with open(os.path.join(file_path, 'audio_files', transcript_id), 'wb') as f:
        f.write(audio_bytes)

    global last_request
    last_request = datetime.utcnow()
    result = json.loads(response.json())
    text = result['text']
    chunks = result['chunks']

    # store transcript in 'transcripts' under name uuid
    data = {
        'id': transcript_id,
        'text': text,
        'chunks': chunks,
        'file_name': file.filename,
        'transcription_name': f'{file.filename} - {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}',
        'created_at': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
    }
    transcripts.insert(data)

    return data


@app.get("/transcriptions", dependencies = [Depends(get_current_user)])
async def get_transcriptions():
    return transcripts.all()


@app.get("/transcriptions/{transcript_id}", dependencies = [Depends(get_current_user)])
async def get_transcription(transcript_id: str):
    # check if transcript exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code = 404, detail = "Transcription not found")

    return transcripts.get(transcript_model.id == transcript_id)


@app.get("/audio/{transcript_id}", dependencies = [Depends(get_current_user)])
async def get_audio_file(transcript_id: str):
    # check if transcript exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code = 404, detail = "Transcription not found")

    # check if audio file exists
    if not os.path.exists(os.path.join(file_path, 'audio_files', transcript_id)):
        raise HTTPException(status_code = 404, detail = "Audio file not found")

    return FileResponse(os.path.join(file_path, 'audio_files', transcript_id))


# delete transcription
@app.delete("/transcriptions/{transcript_id}", dependencies = [Depends(get_current_user)])
async def delete_transcriptions(transcript_id: str):
    # check if id exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code = 404, detail = "Transcription not found")

    # delete audio file from 'audio_files'
    os.remove(os.path.join(file_path, 'audio_files', transcript_id))

    # delete transcript
    transcripts.remove(transcript_model.id == transcript_id)

    return {"status": "ok"}


# route that checks if model is online
@app.get("/server_status")
async def health():
    global last_request
    if last_request is None:
        return {"status": "offline"}
    else:
        if datetime.utcnow() - last_request > timedelta(minutes = 15):
            return {"status": "offline"}
        else:
            return {"status": "online"}


@app.post("/live_server_status")
async def start_server():
    # Send arbitrary data to start server and check if it is online = code different from 502
    data_dict = json.dumps({"inputs": [], "options": {"task": "start_server"}})
    response = requests.post(HUGGINGFACE_API_URL, headers = headers, data = data_dict)
    if response.status_code != 502:
        return {"status": "ok"}
    
    global last_request
    last_request = datetime.utcnow()
    return {"status": "error"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host = "localhost", port = 6545)
