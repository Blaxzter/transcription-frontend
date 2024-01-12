import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from starlette import status
from starlette.responses import FileResponse, Response
from tinydb import Query
from tinydb import TinyDB

from LangModel import LangModel

load_dotenv()

app = FastAPI()
origins = [
    "http://localhost",
    "http://localhost:5173",
    "https://transcribe.fabraham.dev",
    "https://transcribe.fabraham.dev:6544",
    "https://transcribe-api.fabraham.dev",
    "https://transcribe-api.fabraham.dev:6544",
    "http://lehmann-nvidia.3oqsistwe8abycyz.myfritz.net",
    "http://lehmann-nvidia.3oqsistwe8abycyz.myfritz.net:6544",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
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
last_request: datetime.date = None

import torch
print(f"cuda: {torch.cuda.torch.cuda.is_available()}" )

lang_model = LangModel()

transcription_in_progress = False
transcription_text = ''
transcription_chunks = []
transcription_file_name = ''


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


@app.get("/status", dependencies = [Depends(get_current_user)])
async def get_status():
    global transcription_in_progress

    return {"status": "ok", "transcription_in_progress": transcription_in_progress}


def start_transcription_process(transcript_id, audio_file_path):
    global transcription_in_progress
    global transcription_text
    global transcription_chunks
    transcription_in_progress = transcript_id


    def end_callback(end_data):
        process_queue(transcript_id)

    transcription_text = ''
    transcription_chunks = []

    lang_model.transcribe_text(audio_file_path, transcript_id, end_callback)


def process_queue(transcript_id):
    global transcription_in_progress
    global transcription_text
    global transcription_chunks
    global transcription_file_name
    global lang_model

    for data, fished in lang_model.empty_process_queue(transcript_id):
        if fished:
            data = {
                'id': transcript_id,
                'text': transcription_text.strip() if transcription_text else '',
                'chunks': transcription_chunks,
                'file_name': transcription_file_name,
                'transcription_name': f'{transcription_file_name} - {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}',
                'created_at': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            }

            if not transcripts.contains(transcript_model.id == transcript_id):
                # store transcript in 'transcripts' under name uuid
                transcripts.insert(data)
            else:
                transcripts.update(data, transcript_model.id == transcript_id)

            transcription_in_progress = None
        else:
            new_text = data['text'].strip() if data['text'] else ''
            transcription_text = transcription_text + ' ' + new_text
            transcription_chunks.append(dict(
                start = data['start'],
                end = data['end'],
                text = new_text,
            ))


# @dataclass
# class TranscribeRequest:

import subprocess

def cut_audio(input_file, start_time, duration, output_file):

    path_path = Path(output_file)
    # change to append cut_ on filename
    new_output_file = path_path.parent / f'cut_{path_path.name}'

    # Command to cut the audio
    cmd_cut = f'ffmpeg -i "{input_file}" -ss {start_time} -to {duration} -acodec copy "{new_output_file}"'
    subprocess.run(cmd_cut, shell=True)

    # remove old file
    os.remove(input_file)
    # rename new file
    os.rename(new_output_file, output_file)


@app.post("/transcribe", dependencies = [Depends(get_current_user)])
async def upload_audio_file(
    files = File(description="Multiple files as UploadFile"),
    start = Form(),
    end = Form(),
):
    # Rest of the code...
    audio_bytes = await files[0].read()

    if transcription_in_progress:
        raise HTTPException(status_code = 400, detail = "Transcription already in progress")

    transcript_id = str(uuid.uuid4())

    file_type = files[0].filename.split('.')[-1]
    global transcription_file_name
    transcription_file_name = files[0].filename

    audio_file_path = os.path.join(file_path, 'audio_files', transcript_id + '.' + file_type)
    with open(audio_file_path, 'wb') as f:
        f.write(audio_bytes)

    cut_audio(audio_file_path, start, end, audio_file_path)

    start_transcription_process(transcript_id, audio_file_path)

    return {"transcription_id": transcript_id}


@app.get("/transcriptions", dependencies = [Depends(get_current_user)])
async def get_transcriptions():
    return transcripts.all()


@app.get("/transcriptions/{transcript_id}", dependencies = [Depends(get_current_user)])
async def get_transcription(transcript_id: str, response: Response):
    global transcription_in_progress
    global transcription_text
    global transcription_chunks
    global transcription_file_name
    global lang_model

    if transcription_in_progress == transcript_id:
        process_queue(transcript_id)

        response.status_code = status.HTTP_202_ACCEPTED
        return dict(text = transcription_text, chunks = transcription_chunks)

    # check if transcript exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code = 404, detail = "Transcription not found")

    return transcripts.get(transcript_model.id == transcript_id)


@app.get("/audio/{transcript_id}", dependencies = [Depends(get_current_user)])
async def get_audio_file(transcript_id: str):
    # check if transcript exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code = 404, detail = "Transcription not found")

    transcript_data = transcripts.get(transcript_model.id == transcript_id)

    # get file with Path(file_path, 'audio_files', transcript_id . * )
    possible_files = list(Path(os.path.join(file_path, 'audio_files')).glob(f'{transcript_id}.*'))

    # check if audio file exists
    if len(possible_files) == 0:
        raise HTTPException(status_code = 404, detail = "Audio file not found")

    return FileResponse(possible_files[0], media_type = "audio/mpeg", filename = transcript_data['file_name'])


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host = '0.0.0.0', port = 6545)
