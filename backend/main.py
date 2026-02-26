import os
import re
import ssl
import smtplib
import subprocess
import tempfile
import traceback
import uuid
import logging
from logging.handlers import RotatingFileHandler
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
# Logging Configuration
# ----------------------------
# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# Create handlers
console_handler = logging.StreamHandler()
file_handler = RotatingFileHandler(
    os.path.join(log_dir, "transcription.log"),
    maxBytes=10 * 1024 * 1024,  # 10MB per file
    backupCount=5  # Keep 5 backup files
)

# Create formatters and add to handlers
log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(log_format)
file_handler.setFormatter(log_format)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[console_handler, file_handler],
)
logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info("Transcription Backend Starting Up")
logger.info("=" * 80)

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

import torch
print(f"cuda: {torch.cuda.torch.cuda.is_available()}" )

lang_model = LangModel()

transcription_in_progress = False
transcription_text = ""
transcription_chunks = []
transcription_file_name = ""
transcription_error = None
transcription_error_traceback = None


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
        None, description="e.g., video.updated, video.ready, uploading"
    )
    event: Optional[str] = None
    event_id: Optional[str] = None
    event_time: Optional[float] = None  # Can be float timestamp
    version: Optional[str] = None
    object_type: Optional[str] = None  # e.g., "recording", "transcoder"
    object_id: Optional[str] = None
    object_data: Dict[str, Any] = Field(default_factory=dict)  # Wowza uses object_data
    payload: Dict[str, Any] = Field(default_factory=dict)  # Fallback for older format


# ----------------------------
# Wowza Webhook Helper Functions
# ----------------------------
def require_ingest_key(req: Request):
    """Require our own shared secret header from the Worker."""
    logger.info(
        f"[WEBHOOK] Checking ingest key for request from {req.client.host if req.client else 'unknown'}"
    )
    logger.debug(f"[WEBHOOK] Request headers: {dict(req.headers)}")

    if not INGEST_API_KEY:
        logger.warning("[WEBHOOK] INGEST_API_KEY not set - header protection disabled")
        return  # header protection disabled if not set

    key = req.headers.get("x-transcribe-api-key")
    logger.debug(
        f"[WEBHOOK] Received API key: {'***' + key[-4:] if key and len(key) > 4 else 'None'}"
    )

    if not key or key != INGEST_API_KEY:
        logger.error(
            f"[WEBHOOK] Authentication failed - invalid or missing x-transcribe-api-key"
        )
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
      1) object_data.download_url (direct download URL from new webhook format)
      2) payload.encodings[*].video_file_url (preferred, older format)
      3) object_data.encodings[*].video_file_url (new format)
      4) /recordings/{object_id} download_url (for recording objects)
      5) /videos/{object_id} encodings (for video objects, if API creds provided)
      6) Legacy recordings fallback (old payload.id field)
    """
    logger.info("[URL_SEARCH] Starting download URL search")

    # 1) From direct download URL in object_data (new recording webhook format)
    logger.debug("[URL_SEARCH] Checking object_data for direct download_url")
    download_url = webhook.object_data.get("download_url")
    if download_url:
        logger.info("[URL_SEARCH] Found direct download URL in object_data")
        logger.debug(f"[URL_SEARCH] Download URL: {download_url}")
        return download_url, "object_data.download_url"

    # 2) From webhook payload (backwards compatibility)
    logger.debug("[URL_SEARCH] Checking webhook payload for encodings")
    encodings = webhook.payload.get("encodings") or []
    logger.debug(f"[URL_SEARCH] Found {len(encodings)} encodings in payload")

    mp4 = pick_mp4_from_encodings(encodings)
    if mp4:
        logger.info("[URL_SEARCH] Found MP4 URL in webhook payload encodings")
        logger.debug(f"[URL_SEARCH] MP4 URL: {mp4}")
        return mp4, "webhook_payload.encodings"

    # 3) From webhook object_data (new format)
    logger.debug("[URL_SEARCH] Checking webhook object_data for encodings")
    encodings = webhook.object_data.get("encodings") or []
    logger.debug(f"[URL_SEARCH] Found {len(encodings)} encodings in object_data")

    mp4 = pick_mp4_from_encodings(encodings)
    if mp4:
        logger.info("[URL_SEARCH] Found MP4 URL in webhook object_data encodings")
        logger.debug(f"[URL_SEARCH] MP4 URL: {mp4}")
        return mp4, "webhook_object_data.encodings"

    logger.debug("[URL_SEARCH] No suitable MP4 found in webhook payload or object_data")

    # 3) For recording objects, use recordings API directly
    if (
        webhook.object_id
        and webhook.object_type == "recording"
        and (WV_JWT or (WSC_API_KEY and WSC_ACCESS_KEY))
    ):
        logger.info(
            f"[URL_SEARCH] Trying recordings API for recording {webhook.object_id}"
        )
        try:
            durl = wowza_get_recording_download_url(webhook.object_id)
            if durl:
                logger.info("[URL_SEARCH] Found download URL via recordings API")
                logger.debug(f"[URL_SEARCH] Download URL: {durl}")
                return durl, "recordings.api"
        except Exception as e:
            logger.warning(f"[URL_SEARCH] Failed to query recordings API: {e}")

    # 4) For video objects, query videos API if we have creds
    elif webhook.object_id and (WV_JWT or (WSC_API_KEY and WSC_ACCESS_KEY)):
        logger.info(f"[URL_SEARCH] Querying Wowza API for video {webhook.object_id}")
        try:
            enc = wowza_get_video_encodings(webhook.object_id)
            logger.debug(f"[URL_SEARCH] API returned {len(enc)} encodings")
            mp4 = pick_mp4_from_encodings(enc)
            if mp4:
                logger.info("[URL_SEARCH] Found MP4 URL via Wowza videos API")
                logger.debug(f"[URL_SEARCH] MP4 URL: {mp4}")
                return mp4, "videos.api"
        except Exception as e:
            logger.warning(f"[URL_SEARCH] Failed to query videos API: {e}")

    logger.debug("[URL_SEARCH] No suitable MP4 found via API")

    # 5) Legacy recordings fallback (old payload.id field)
    rec_id = webhook.payload.get("id")
    if (
        rec_id
        and isinstance(rec_id, str)
        and len(rec_id) <= 16
        and (WV_JWT or (WSC_API_KEY and WSC_ACCESS_KEY))
    ):
        logger.info(f"[URL_SEARCH] Trying recordings API for legacy recording {rec_id}")
        try:
            durl = wowza_get_recording_download_url(rec_id)
            if durl:
                logger.info("[URL_SEARCH] Found download URL via legacy recordings API")
                logger.debug(f"[URL_SEARCH] Download URL: {durl}")
                return durl, "recordings.api.legacy"
        except Exception as e:
            logger.warning(f"[URL_SEARCH] Failed to query legacy recordings API: {e}")

    logger.warning("[URL_SEARCH] No download URL found via any method")
    return None, "not_found"


def stream_download(url: str, suffix: str = ".mp4") -> str:
    """Stream a big file to a temp path; return file path."""
    logger.info(f"[DOWNLOAD] Starting download from URL")
    logger.debug(f"[DOWNLOAD] URL: {url}")
    logger.debug(f"[DOWNLOAD] File suffix: {suffix}")

    # Create temp directory if it doesn't exist
    temp_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=temp_dir) as f:
        temp_path = f.name
        logger.debug(f"[DOWNLOAD] Temporary file: {temp_path}")

        with http_session.get(
            url, headers=headers, stream=True, timeout=HTTP_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            logger.info(
                f"[DOWNLOAD] HTTP {resp.status_code} - Content-Length: {resp.headers.get('content-length', 'unknown')}"
            )

            downloaded_bytes = 0
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded_bytes += len(chunk)

            logger.info(f"[DOWNLOAD] Download completed - {downloaded_bytes} bytes")
        return temp_path


def transcribe_with_whisper(video_path: str) -> str:
    """Transcribe using openai-whisper through the LangModel."""
    logger.info(f"[TRANSCRIBE] Starting transcription of file: {video_path}")

    if lang_model is None or lang_model.model is None:
        logger.error("[TRANSCRIBE] LangModel not loaded")
        raise RuntimeError("LangModel not loaded")

    logger.info(
        f"[TRANSCRIBE] Using model: {lang_model.model_name if hasattr(lang_model, 'model_name') else 'unknown'}"
    )

    force_lang = (
        WHISPER_LANGUAGE
        if WHISPER_LANGUAGE and WHISPER_LANGUAGE.lower() != "auto"
        else None
    )
    fp16_ok = WHISPER_FP16 and torch.cuda.is_available()

    logger.info(f"[TRANSCRIBE] Language setting: {force_lang or 'auto-detect'}")
    logger.info(f"[TRANSCRIBE] FP16 enabled: {fp16_ok}")
    logger.info(f"[TRANSCRIBE] CUDA available: {torch.cuda.is_available()}")

    try:
        logger.info("[TRANSCRIBE] Starting Whisper transcription...")
        result = lang_model.model.transcribe(
            audio=video_path,
            language="de",  # None → autodetect
            verbose=False,
            fp16=fp16_ok,
        )
        logger.info("[TRANSCRIBE] Whisper transcription completed")

    except Exception as e:
        logger.error(f"[TRANSCRIBE] Whisper transcription failed: {e}")
        raise

    text = (result.get("text") or "").strip()
    if text:
        logger.info(f"[TRANSCRIBE] Extracted text: {len(text)} characters")
        logger.debug(f"[TRANSCRIBE] Text preview: {text[:200]}...")
        return text

    # Very rare: rebuild from segments
    logger.warning("[TRANSCRIBE] No text found, attempting to rebuild from segments")
    segs = result.get("segments") or []
    logger.info(f"[TRANSCRIBE] Found {len(segs)} segments")

    rebuilt_text = "\n".join(s.get("text", "").strip() for s in segs if s.get("text"))
    logger.info(f"[TRANSCRIBE] Rebuilt text: {len(rebuilt_text)} characters")

    return rebuilt_text


def send_email_with_attachment(
    subject: str, body_text: str, filename: str, file_bytes: bytes
):
    logger.info(f"[EMAIL] Preparing to send email: {subject}")
    logger.info(f"[EMAIL] Attachment filename: {filename}")
    logger.info(f"[EMAIL] Attachment size: {len(file_bytes)} bytes")

    if not (SMTP_USERNAME and SMTP_PASSWORD and EMAIL_TO and EMAIL_FROM):
        logger.error("[EMAIL] Missing email configuration")
        logger.debug(
            f"[EMAIL] Config status - USERNAME: {'set' if SMTP_USERNAME else 'missing'}, PASSWORD: {'set' if SMTP_PASSWORD else 'missing'}, TO: {'set' if EMAIL_TO else 'missing'}, FROM: {'set' if EMAIL_FROM else 'missing'}"
        )
        raise RuntimeError(
            "Missing email config: set GMAIL_USERNAME, GMAIL_PASSWORD, TRANSCRIBE_EMAIL_TO"
        )

    logger.info(f"[EMAIL] Sending from {EMAIL_FROM} to {EMAIL_TO}")
    logger.info(f"[EMAIL] Using SMTP server: {SMTP_HOST}:{SMTP_PORT}")

    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.set_content(body_text)
        msg.add_attachment(
            file_bytes, maintype="text", subtype="plain", filename=filename
        )
        logger.debug("[EMAIL] Email message constructed")

        context = ssl.create_default_context()
        logger.debug("[EMAIL] Connecting to SMTP server...")

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            logger.debug("[EMAIL] Starting TLS...")
            server.starttls(context=context)

            logger.debug("[EMAIL] Authenticating...")
            server.login(SMTP_USERNAME, SMTP_PASSWORD)

            logger.debug("[EMAIL] Sending message...")
            server.send_message(msg)

        logger.info("[EMAIL] Email sent successfully")

    except Exception as e:
        logger.error(f"[EMAIL] Failed to send email: {e}")
        raise


def looks_ready(event_type: str, payload: Dict[str, Any]) -> bool:
    """Gate processing to 'ready/finished' events."""
    logger.debug(f"[READY_CHECK] Checking if event is ready - type: {event_type}")
    logger.debug(f"[READY_CHECK] Payload state: {payload.get('state', 'not_set')}")

    # Recording completion events (new recording webhook format)
    if event_type == "completed":
        logger.info(
            "[READY_CHECK] Event is completed (recording finished) - processing"
        )
        return True

    # Video upload events (original logic)
    if event_type == "video.ready":
        logger.info("[READY_CHECK] Event is video.ready - processing")
        return True
    if (
        event_type == "video.updated"
        and str(payload.get("state", "")).upper() == "FINISHED"
    ):
        logger.info(
            "[READY_CHECK] Event is video.updated with FINISHED state - processing"
        )
        return True

    # Recording events (livestream recordings)
    if event_type == "uploading":
        logger.info("[READY_CHECK] Event is uploading (recording ready) - processing")
        return True

    logger.info(f"[READY_CHECK] Event {event_type} is not ready - skipping")
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

    health_info = {
        "status": "ok",
        "model": model_name,
        "model_loaded": model_loaded,
        "cuda": torch.cuda.is_available(),
        "language": (WHISPER_LANGUAGE or "auto"),
        "email_to": EMAIL_TO,
    }

    logger.info(
        f"[HEALTH] Health check requested - Model: {model_name}, CUDA: {torch.cuda.is_available()}"
    )
    return health_info


@app.post("/webhook/wowza")
async def wowza_webhook(request: Request, background: BackgroundTasks):
    logger.info("[WEBHOOK] Received Wowza webhook request")
    logger.info(f"[WEBHOOK] Request method: {request.method}")
    logger.info(f"[WEBHOOK] Request URL: {request.url}")
    logger.info(
        f"[WEBHOOK] Client: {request.client.host if request.client else 'unknown'}"
    )
    logger.debug(f"[WEBHOOK] All headers: {dict(request.headers)}")

    require_ingest_key(request)

    try:
        data = await request.json()
        logger.info(f"[WEBHOOK] Successfully parsed JSON payload with {len(data)} keys")
        logger.debug(f"[WEBHOOK] Raw payload: {data}")
    except Exception as e:
        logger.error(f"[WEBHOOK] Failed to parse JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Normalize `event` → `event_type` if needed
    if "event_type" not in data and "event" in data:
        logger.info(f"[WEBHOOK] Normalizing 'event' to 'event_type': {data['event']}")
        data["event_type"] = data["event"]

    try:
        webhook = WowzaWebhook.model_validate(data)
        logger.info(f"[WEBHOOK] Successfully validated webhook data")
        logger.info(f"[WEBHOOK] Event type: {webhook.event_type}")
        logger.info(f"[WEBHOOK] Object ID: {webhook.object_id}")
        logger.info(f"[WEBHOOK] Event ID: {webhook.event_id}")
        logger.debug(f"[WEBHOOK] Payload keys: {list(webhook.payload.keys())}")
    except Exception as e:
        logger.error(f"[WEBHOOK] Failed to validate payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # Process in background, ACK fast
    logger.info(f"[WEBHOOK] Adding webhook processing task to background queue")
    background.add_task(process_webhook, webhook.model_dump())
    logger.info(f"[WEBHOOK] Webhook acknowledged and queued for processing")
    return {"received": True}


def process_webhook(webhook_dict: Dict[str, Any]):
    logger.info("[PROCESS] Starting webhook processing in background task")
    webhook = WowzaWebhook(**webhook_dict)
    event_type = webhook.event_type or ""

    logger.info(f"[PROCESS] Processing event: {event_type}")
    logger.info(f"[PROCESS] Object ID: {webhook.object_id}")
    logger.debug(f"[PROCESS] Full webhook data: {webhook_dict}")

    if not looks_ready(event_type, webhook.payload):
        logger.info(f"[PROCESS] Event {event_type} is not a ready event - ignoring")
        return  # ignore non-ready events

    logger.info(
        f"[PROCESS] Event indicates video is ready - proceeding with processing"
    )

    download_url, source = find_download_url(webhook)
    logger.info(f"[PROCESS] Download URL search result - Source: {source}")

    if not download_url:
        logger.error(
            "[PROCESS] No download URL found (payload may lack encodings and no Wowza creds set)"
        )
        logger.debug(
            f"[PROCESS] Webhook payload for failed URL lookup: {webhook.payload}"
        )
        return

    logger.info(f"[PROCESS] Found download URL from {source}")
    logger.debug(f"[PROCESS] Download URL: {download_url}")

    temp_path = None
    try:
        logger.info("[PROCESS] Starting video download")
        # Preserve real extension if present
        suffix = ".mp4"
        m = re.search(r"\.(mp4|mov|m4a|mkv)(?:\?|$)", download_url, flags=re.I)
        if m:
            suffix = "." + m.group(1).lower()
            logger.debug(f"[PROCESS] Detected file extension: {suffix}")

        temp_path = stream_download(download_url, suffix=suffix)
        logger.info(f"[PROCESS] Video downloaded to temporary file: {temp_path}")

        logger.info("[PROCESS] Starting transcription")
        transcript = transcribe_with_whisper(temp_path)
        logger.info(f"[PROCESS] Transcription completed - {len(transcript)} characters")
        logger.debug(f"[PROCESS] Transcript preview: {transcript[:200]}...")

        video_name = (
            webhook.object_data.get("file_name")
            or webhook.payload.get("name")
            or f"wowza_video_{webhook.object_id or 'unknown'}"
        )
        logger.info(f"[PROCESS] Video name: {video_name}")

        subject = f"[Transcript] {video_name}"
        preview = transcript[:400] + ("…" if len(transcript) > 400 else "")
        body = (
            f"Event: {event_type}\n"
            f"Source: {source}\n"
            f"Video ID: {webhook.object_id}\n\n"
            f"Preview:\n{preview}\n"
        )

        logger.info("[PROCESS] Sending email with transcript")
        send_email_with_attachment(
            subject=subject,
            body_text=body,
            filename=f"{video_name}.txt",
            file_bytes=transcript.encode("utf-8"),
        )
        logger.info("[PROCESS] Email sent successfully")

    except Exception as e:
        logger.error(f"[PROCESS] Error during webhook processing: {e}")
        logger.error(f"[PROCESS] Traceback: {traceback.format_exc()}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug(f"[PROCESS] Cleaned up temporary file: {temp_path}")
            except Exception as cleanup_err:
                logger.warning(
                    f"[PROCESS] Failed to cleanup temp file {temp_path}: {cleanup_err}"
                )


@app.get("/status", dependencies=[Depends(get_current_user)])
async def get_status():
    global transcription_in_progress

    return {"status": "ok", "transcription_in_progress": transcription_in_progress}


def start_transcription_process(transcript_id, audio_file_path):
    global transcription_in_progress
    global transcription_text
    global transcription_chunks
    global transcription_error
    global transcription_error_traceback
    
    logger.info(f"[TRANSCRIBE] Starting transcription process for job {transcript_id}")
    logger.info(f"[TRANSCRIBE] Audio file: {audio_file_path}")
    
    transcription_in_progress = transcript_id
    transcription_error = None
    transcription_error_traceback = None

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
    global transcription_error
    global transcription_error_traceback
    global lang_model

    for data, fished in lang_model.empty_process_queue(transcript_id):
        if fished:
            # Check if this is an error
            if data.get("is_error"):
                logger.error(f"[TRANSCRIBE] Job {transcript_id} failed with error: {data.get('error')}")
                logger.error(f"[TRANSCRIBE] Traceback:\n{data.get('traceback')}")
                transcription_error = data.get("error")
                transcription_error_traceback = data.get("traceback")
                transcription_in_progress = None
                # Don't store the transcription in the database if it failed
                return
            
            # Success case
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
                logger.info(f"[TRANSCRIBE] Job {transcript_id} completed successfully and saved to database")
            else:
                transcripts.update(data, transcript_model.id == transcript_id)
                logger.info(f"[TRANSCRIBE] Job {transcript_id} completed successfully and updated in database")

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
    logger.info(f"[AUDIO] Cutting audio file: {input_file}")
    logger.info(f"[AUDIO] Start time: {start_time}, Duration: {duration}")

    path_path = Path(output_file)
    # change to append cut_ on filename
    new_output_file = path_path.parent / f"cut_{path_path.name}"

    # Command to cut the audio
    cmd_cut = f'ffmpeg -i "{input_file}" -ss {start_time} -to {duration} -acodec copy "{new_output_file}"'
    
    try:
        result = subprocess.run(cmd_cut, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"[AUDIO] FFmpeg error: {result.stderr}")
            raise Exception(f"Failed to cut audio: {result.stderr}")
        logger.info(f"[AUDIO] Audio cut successfully")
    except Exception as e:
        logger.error(f"[AUDIO] Failed to cut audio: {str(e)}")
        raise

    # remove old file
    os.remove(input_file)
    # rename new file
    os.rename(new_output_file, output_file)
    logger.info(f"[AUDIO] Audio file saved to: {output_file}")


@app.post("/transcribe", dependencies=[Depends(get_current_user)])
async def upload_audio_file(
    files=File(description="Multiple files as UploadFile"),
    start=Form(),
    end=Form(),
):
    logger.info(f"[API] Received transcription request for file: {files.filename}")
    logger.info(f"[API] Start: {start}, End: {end}")
    
    # Rest of the code...
    audio_bytes = await files.read()
    logger.info(f"[API] File size: {len(audio_bytes)} bytes")

    if transcription_in_progress:
        logger.warning(f"[API] Transcription already in progress: {transcription_in_progress}")
        raise HTTPException(status_code=400, detail="Transcription already in progress")

    transcript_id = str(uuid.uuid4())
    logger.info(f"[API] Generated transcript ID: {transcript_id}")

    file_type = files.filename.split(".")[-1]
    global transcription_file_name
    transcription_file_name = files.filename

    audio_file_path = os.path.join(
        file_path, "audio_files", transcript_id + "." + file_type
    )
    
    try:
        with open(audio_file_path, "wb") as f:
            f.write(audio_bytes)
        logger.info(f"[API] Audio file saved to: {audio_file_path}")

        cut_audio(audio_file_path, start, end, audio_file_path)

        start_transcription_process(transcript_id, audio_file_path)
        
        logger.info(f"[API] Transcription process started successfully for {transcript_id}")
        return {"transcription_id": transcript_id}
    except Exception as e:
        logger.error(f"[API] Failed to process audio file: {str(e)}")
        logger.error(f"[API] Traceback: {traceback.format_exc()}")
        # Clean up the file if it was created
        if os.path.exists(audio_file_path):
            try:
                os.remove(audio_file_path)
                logger.info(f"[API] Cleaned up audio file: {audio_file_path}")
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to process audio file: {str(e)}")


@app.get("/transcriptions", dependencies=[Depends(get_current_user)])
async def get_transcriptions():
    return transcripts.all()


@app.get("/transcriptions/{transcript_id}", dependencies=[Depends(get_current_user)])
async def get_transcription(transcript_id: str, response: Response):
    global transcription_in_progress
    global transcription_text
    global transcription_chunks
    global transcription_file_name
    global transcription_error
    global transcription_error_traceback
    global lang_model

    if transcription_in_progress == transcript_id:
        process_queue(transcript_id)

        # Check if there was an error
        if transcription_error:
            logger.error(f"[API] Returning error status for job {transcript_id}")
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return dict(
                status="error",
                error=transcription_error,
                traceback=transcription_error_traceback,
                text=transcription_text,
                chunks=transcription_chunks
            )

        response.status_code = status.HTTP_202_ACCEPTED
        return dict(
            status="in_progress",
            text=transcription_text, 
            chunks=transcription_chunks
        )

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
