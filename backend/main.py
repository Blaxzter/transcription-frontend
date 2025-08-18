import os
import re
import ssl
import smtplib
import subprocess
import tempfile
import traceback
import uuid
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Any, Dict, Tuple, List

import bcrypt
import jwt
import requests
import torch
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    Form,
    File,
    Request,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from starlette import status
from starlette.responses import FileResponse, Response
from tinydb import Query
from tinydb import TinyDB

from LangModel import LangModel

load_dotenv()

# ----------------------------
# Wowza Webhook Config
# ----------------------------
# Relay / webhook security (from your Cloudflare Worker)
INGEST_API_KEY = os.getenv(
    "INGEST_API_KEY"
)  # must match TRANSCRIBE_API_KEY used by the Worker

# Email settings (Gmail SMTP)
SMTP_HOST = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("GMAIL_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("GMAIL_USERNAME")
SMTP_PASSWORD = os.getenv("GMAIL_PASSWORD")  # Use a Gmail App Password
EMAIL_TO = os.getenv("TRANSCRIBE_EMAIL_TO")  # recipient
EMAIL_FROM = os.getenv(
    "TRANSCRIBE_EMAIL_FROM", SMTP_USERNAME
)  # sender (your Gmail, typically)

# Wowza API (optional; only used if we must look up encodings)
WOWZA_API_HOST = os.getenv("WOWZA_API_HOST", "https://api.video.wowza.com")
WOWZA_API_VERSION = os.getenv("WOWZA_API_VERSION", "v2.0")
WV_JWT = os.getenv("WV_JWT")  # Bearer token (new style)
WSC_API_KEY = os.getenv("WSC_API_KEY")  # Legacy header
WSC_ACCESS_KEY = os.getenv("WSC_ACCESS_KEY")  # Legacy header

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))

# Whisper model configuration
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "large-v2")
WHISPER_DOWNLOAD_DIR = os.getenv("WHISPER_MODEL_DIR")  # optional cache dir
# Set WHISPER_LANGUAGE to e.g. "de" to force German. Leave unset/empty/"auto" for autodetect.
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "").strip()
# On Jetson you may prefer fp16=False for stability; set to "1" to force fp16 when CUDA is available
WHISPER_FP16 = os.getenv("WHISPER_FP16", "0") in {"1", "true", "True"}

# ----------------------------
# App state
# ----------------------------
lang_model: Optional[LangModel] = None
http_session = requests.Session()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the language model
    global lang_model
    print("[startup] Initializing LangModel...")
    lang_model = LangModel()
    print(f"[startup] LangModel loaded with model: {lang_model.model_name}")
    print(f"[startup] torch.cuda.is_available()={torch.cuda.is_available()}")

    yield

    http_session.close()


# Existing config
app = FastAPI(
    title="Transcription Backend with Wowza Webhooks",
    version="2.0.0",
    lifespan=lifespan,
)

# Load CORS origins from environment variable
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env:
    origins = [
        origin.strip() for origin in cors_origins_env.split(",") if origin.strip()
    ]
else:
    # Fallback origins if not set in environment
    origins = [
        "http://localhost",
        "http://localhost:5173",
    ]

print(f"[startup] CORS origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

file_path = os.path.dirname(__file__)
os.makedirs(os.path.join(file_path, "audio_files"), exist_ok=True)

SECRET_KEY = os.getenv("SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 3000

path = os.path.dirname(__file__)
db = TinyDB(os.path.join(path, "db.json"))
transcript_model = Query()
transcripts = db.table("transcribes")
job_db = db.table("jobs")


def hash_password(pw):
    pwhash = bcrypt.hashpw(pw.encode("utf8"), bcrypt.gensalt())
    return pwhash.decode("utf8")


HUGGINGFACE_API_URL = os.getenv("HUGGINGFACE_API_URL")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
USERS = {
    os.getenv("TRANSCRIPT_USER"): hash_password(os.environ.get("TRANSCRIPT_PASSWORD"))
}

headers = {
    "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
    "Content-Type": "application/json",
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
last_request: datetime.date = None

transcription_in_progress = False
transcription_text = ""
transcription_chunks = []
transcription_file_name = ""


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# ----------------------------
# Wowza Webhook Pydantic models
# ----------------------------
class WowzaWebhook(BaseModel):
    # Wowza sometimes uses `event`, sometimes `event_type` depending on product/era
    event_type: Optional[str] = Field(
        None, description="e.g., video.updated, video.ready"
    )
    event: Optional[str] = None
    event_id: Optional[str] = None
    event_time: Optional[str] = None
    object_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


# ----------------------------
# Wowza Webhook Helper Functions
# ----------------------------
def require_ingest_key(req: Request):
    """Require our own shared secret header from the Worker."""
    if not INGEST_API_KEY:
        return  # header protection disabled if not set
    key = req.headers.get("x-transcribe-api-key")
    if not key or key != INGEST_API_KEY:
        raise HTTPException(
            status_code=401, detail="Bad or missing x-transcribe-api-key"
        )


def auth_headers() -> Dict[str, str]:
    """Build Wowza API auth headers if provided (optional fallback lookup)."""
    headers = {"Content-Type": "application/json"}
    if WV_JWT:
        headers["Authorization"] = f"Bearer {WV_JWT}"
    if WSC_API_KEY and WSC_ACCESS_KEY:
        headers["wsc-api-key"] = WSC_API_KEY
        headers["wsc-access-key"] = WSC_ACCESS_KEY
    return headers


def pick_mp4_from_encodings(encodings: List[Dict[str, Any]]) -> Optional[str]:
    """Pick the highest-res MP4 URL from an encodings array."""
    best = None
    best_h = -1
    for e in encodings or []:
        container = (e.get("video_container") or "").lower()
        url = e.get("video_file_url")
        h = int(e.get("height") or 0)
        if container == "mp4" and url:
            if h >= best_h:
                best_h = h
                best = url
    return best


def wowza_get_video_encodings(video_id: str) -> List[Dict[str, Any]]:
    """GET /api/v2.0/videos/{id} → encodings (optional path if webhook lacks URLs)."""
    url = f"{WOWZA_API_HOST}/api/{WOWZA_API_VERSION}/videos/{video_id}"
    r = http_session.get(url, headers=auth_headers(), timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("video", {}).get("encodings", []) or data.get("encodings", []) or []


def wowza_get_recording_download_url(recording_id: str) -> Optional[str]:
    """GET /api/v2.0/recordings/{id} → download_url (optional fallback)."""
    url = f"{WOWZA_API_HOST}/api/{WOWZA_API_VERSION}/recordings/{recording_id}"
    r = http_session.get(url, headers=auth_headers(), timeout=HTTP_TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    return data.get("recording", {}).get("download_url")


def find_download_url(webhook: WowzaWebhook) -> Tuple[Optional[str], str]:
    """
    Try, in order:
      1) payload.encodings[*].video_file_url (preferred)
      2) /videos/{object_id} encodings (if API creds provided)
      3) /recordings/{payload.id} download_url (fallback)
    """
    # 1) From webhook payload
    mp4 = pick_mp4_from_encodings(webhook.payload.get("encodings") or [])
    if mp4:
        return mp4, "webhook_payload.encodings"

    # 2) Query videos API if we have an object_id and creds
    if webhook.object_id and (WV_JWT or (WSC_API_KEY and WSC_ACCESS_KEY)):
        try:
            enc = wowza_get_video_encodings(webhook.object_id)
            mp4 = pick_mp4_from_encodings(enc)
            if mp4:
                return mp4, "videos.api"
        except Exception:
            pass

    # 3) recordings fallback
    rec_id = webhook.payload.get("id")
    if (
        rec_id
        and isinstance(rec_id, str)
        and len(rec_id) <= 16
        and (WV_JWT or (WSC_API_KEY and WSC_ACCESS_KEY))
    ):
        try:
            durl = wowza_get_recording_download_url(rec_id)
            if durl:
                return durl, "recordings.api"
        except Exception:
            pass

    return None, "not_found"


def stream_download(url: str, suffix: str = ".mp4") -> str:
    """Stream a big file to a temp path; return file path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        with http_session.get(url, stream=True, timeout=HTTP_TIMEOUT) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        return f.name


def transcribe_with_whisper(video_path: str) -> str:
    """Transcribe using openai-whisper through the LangModel."""
    if lang_model is None or lang_model.model is None:
        raise RuntimeError("LangModel not loaded")

    force_lang = (
        WHISPER_LANGUAGE
        if WHISPER_LANGUAGE and WHISPER_LANGUAGE.lower() != "auto"
        else None
    )
    fp16_ok = WHISPER_FP16 and torch.cuda.is_available()

    result = lang_model.model.transcribe(
        audio=video_path,
        language=force_lang,  # None → autodetect
        verbose=False,
        fp16=fp16_ok,
    )
    text = (result.get("text") or "").strip()
    if text:
        return text

    # Very rare: rebuild from segments
    segs = result.get("segments") or []
    return "\n".join(s.get("text", "").strip() for s in segs if s.get("text"))


def send_email_with_attachment(
    subject: str, body_text: str, filename: str, file_bytes: bytes
):
    if not (SMTP_USERNAME and SMTP_PASSWORD and EMAIL_TO and EMAIL_FROM):
        raise RuntimeError(
            "Missing email config: set GMAIL_USERNAME, GMAIL_PASSWORD, TRANSCRIBE_EMAIL_TO"
        )

    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body_text)
    msg.add_attachment(file_bytes, maintype="text", subtype="plain", filename=filename)

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


def looks_ready(event_type: str, payload: Dict[str, Any]) -> bool:
    """Gate processing to 'ready/finished' events."""
    if event_type == "video.ready":
        return True
    if (
        event_type == "video.updated"
        and str(payload.get("state", "")).upper() == "FINISHED"
    ):
        return True
    return False


def check_password(pw, hashed_pw):
    expected_hash = hashed_pw.encode("utf8")
    return bcrypt.checkpw(pw.encode("utf8"), expected_hash)


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


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
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401, detail="Could not validate credentials"
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except jwt.PyJWTError:
        raise credentials_exception
    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/")
def health():
    model_name = lang_model.model_name if lang_model else "not_loaded"
    model_loaded = lang_model is not None and lang_model.model is not None
    return {
        "status": "ok",
        "model": model_name,
        "model_loaded": model_loaded,
        "cuda": torch.cuda.is_available(),
        "language": (WHISPER_LANGUAGE or "auto"),
        "email_to": EMAIL_TO,
    }


@app.post("/webhook/wowza")
async def wowza_webhook(request: Request, background: BackgroundTasks):
    require_ingest_key(request)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Normalize `event` → `event_type` if needed
    if "event_type" not in data and "event" in data:
        data["event_type"] = data["event"]

    try:
        webhook = WowzaWebhook.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # Process in background, ACK fast
    background.add_task(process_webhook, webhook.model_dump())
    return {"received": True}


def process_webhook(webhook_dict: Dict[str, Any]):
    webhook = WowzaWebhook(**webhook_dict)
    event_type = webhook.event_type or ""

    if not looks_ready(event_type, webhook.payload):
        return  # ignore non-ready events

    download_url, source = find_download_url(webhook)
    if not download_url:
        print(
            "[process] No download URL found (payload may lack encodings and no Wowza creds set)."
        )
        return

    temp_path = None
    try:
        # Preserve real extension if present
        suffix = ".mp4"
        m = re.search(r"\.(mp4|mov|m4a|mkv)(?:\?|$)", download_url, flags=re.I)
        if m:
            suffix = "." + m.group(1).lower()

        temp_path = stream_download(download_url, suffix=suffix)
        transcript = transcribe_with_whisper(temp_path)

        video_name = (
            webhook.payload.get("name")
            or f"wowza_video_{webhook.object_id or 'unknown'}"
        )
        subject = f"[Transcript] {video_name}"
        preview = transcript[:400] + ("…" if len(transcript) > 400 else "")
        body = (
            f"Event: {event_type}\n"
            f"Source: {source}\n"
            f"Video ID: {webhook.object_id}\n\n"
            f"Preview:\n{preview}\n"
        )

        send_email_with_attachment(
            subject=subject,
            body_text=body,
            filename=f"{video_name}.txt",
            file_bytes=transcript.encode("utf-8"),
        )
    except Exception as e:
        traceback.print_exc()
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@app.get("/status", dependencies=[Depends(get_current_user)])
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

    transcription_text = ""
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
                "id": transcript_id,
                "text": transcription_text.strip() if transcription_text else "",
                "chunks": transcription_chunks,
                "file_name": transcription_file_name,
                "transcription_name": f'{transcription_file_name} - {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}',
                "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            }

            if not transcripts.contains(transcript_model.id == transcript_id):
                # store transcript in 'transcripts' under name uuid
                transcripts.insert(data)
            else:
                transcripts.update(data, transcript_model.id == transcript_id)

            transcription_in_progress = None
        else:
            new_text = data["text"].strip() if data["text"] else ""
            transcription_text = transcription_text + " " + new_text
            transcription_chunks.append(
                dict(
                    start=data["start"],
                    end=data["end"],
                    text=new_text,
                )
            )


# @dataclass
# class TranscribeRequest:


def cut_audio(input_file, start_time, duration, output_file):

    path_path = Path(output_file)
    # change to append cut_ on filename
    new_output_file = path_path.parent / f"cut_{path_path.name}"

    # Command to cut the audio
    cmd_cut = f'ffmpeg -i "{input_file}" -ss {start_time} -to {duration} -acodec copy "{new_output_file}"'
    subprocess.run(cmd_cut, shell=True)

    # remove old file
    os.remove(input_file)
    # rename new file
    os.rename(new_output_file, output_file)


@app.post("/transcribe", dependencies=[Depends(get_current_user)])
async def upload_audio_file(
    files=File(description="Multiple files as UploadFile"),
    start=Form(),
    end=Form(),
):
    # Rest of the code...
    audio_bytes = await files.read()

    if transcription_in_progress:
        raise HTTPException(status_code=400, detail="Transcription already in progress")

    transcript_id = str(uuid.uuid4())

    file_type = files.filename.split(".")[-1]
    global transcription_file_name
    transcription_file_name = files.filename

    audio_file_path = os.path.join(
        file_path, "audio_files", transcript_id + "." + file_type
    )
    with open(audio_file_path, "wb") as f:
        f.write(audio_bytes)

    cut_audio(audio_file_path, start, end, audio_file_path)

    start_transcription_process(transcript_id, audio_file_path)

    return {"transcription_id": transcript_id}


@app.get("/transcriptions", dependencies=[Depends(get_current_user)])
async def get_transcriptions():
    return transcripts.all()


@app.get("/transcriptions/{transcript_id}", dependencies=[Depends(get_current_user)])
async def get_transcription(transcript_id: str, response: Response):
    global transcription_in_progress
    global transcription_text
    global transcription_chunks
    global transcription_file_name
    global lang_model

    if transcription_in_progress == transcript_id:
        process_queue(transcript_id)

        response.status_code = status.HTTP_202_ACCEPTED
        return dict(text=transcription_text, chunks=transcription_chunks)

    # check if transcript exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code=404, detail="Transcription not found")

    return transcripts.get(transcript_model.id == transcript_id)


@app.get("/audio/{transcript_id}", dependencies=[Depends(get_current_user)])
async def get_audio_file(transcript_id: str):
    # check if transcript exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code=404, detail="Transcription not found")

    transcript_data = transcripts.get(transcript_model.id == transcript_id)

    # get file with Path(file_path, 'audio_files', transcript_id . * )
    possible_files = list(
        Path(os.path.join(file_path, "audio_files")).glob(f"{transcript_id}*")
    )

    # check if audio file exists
    if len(possible_files) == 0:
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        possible_files[0],
        media_type="audio/mpeg",
        filename=transcript_data["file_name"],
    )


# delete transcription
@app.delete("/transcriptions/{transcript_id}", dependencies=[Depends(get_current_user)])
async def delete_transcriptions(transcript_id: str):
    # check if id exists
    if not transcripts.contains(transcript_model.id == transcript_id):
        raise HTTPException(status_code=404, detail="Transcription not found")

    possible_files = list(
        Path(os.path.join(file_path, "audio_files")).glob(f"{transcript_id}*")
    )

    # delete audio file from 'audio_files'
    os.remove(possible_files[0])

    # delete transcript
    transcripts.remove(transcript_model.id == transcript_id)

    return {"status": "ok"}


@app.post("/stop-transcription", dependencies=[Depends(get_current_user)])
async def stop_transcription():
    global transcription_in_progress
    global lang_model

    if not transcription_in_progress:
        raise HTTPException(status_code=400, detail="No transcription in progress")

    transcript_id = transcription_in_progress
    # Stop the transcription process
    lang_model.stop_transcription(transcript_id)

    # Update the transcription status
    if transcripts.contains(transcript_model.id == transcript_id):
        transcripts.update({"completed": True}, transcript_model.id == transcript_id)

    transcription_in_progress = False
    return {"status": "stopped", "transcription_id": transcript_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=6545)
