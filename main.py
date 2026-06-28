import io
import mimetypes
import os

import cloudinary
import cloudinary.uploader
import cloudinary.api
import requests as http_requests

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
    secure=True
)

FIXED_PUBLIC_ID = "voice_studio_latest"

app = FastAPI(title="Voice Clone API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_TYPES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
    "audio/ogg", "audio/flac", "audio/aac", "audio/m4a",
    "audio/x-m4a", "application/octet-stream"
}


@app.get("/")
async def root():
    return {"status": "healthy"}


@app.get("/test-cloudinary")
async def test_cloudinary():
    try:
        result = cloudinary.api.ping()
        return {"cloudinary": "connected", "response": result}
    except cloudinary.api.Error as e:
        return {"cloudinary": "auth_failed", "error": str(e)}
    except Exception as e:
        return {"cloudinary": "error", "error": str(e)}


@app.get("/debug")
async def debug():
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    api_key = os.environ.get("CLOUDINARY_API_KEY", "")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
    return {
        "CLOUDINARY_CLOUD_NAME": cloud_name if cloud_name else "NOT SET",
        "CLOUDINARY_API_KEY": api_key[:6] + "..." if api_key else "NOT SET",
        "CLOUDINARY_API_SECRET": "SET" if api_secret else "NOT SET",
    }


@app.post("/receive")
async def receive_audio(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported audio format."
        )

    try:
        contents = await file.read()
        ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "mp3"

        result = cloudinary.uploader.upload(
            contents,
            public_id=FIXED_PUBLIC_ID,
            resource_type="video",
            overwrite=True,
            format=ext,
        )

        return {
            "status": "success",
            "message": f"File '{file.filename}' uploaded successfully.",
            "filename": file.filename,
            "url": result["secure_url"]
        }

    except cloudinary.api.Error as e:
        raise HTTPException(status_code=502, detail=f"Cloudinary error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/send")
async def send_audio():
    try:
        resource = cloudinary.api.resource(FIXED_PUBLIC_ID, resource_type="video")
        file_url = resource["secure_url"]
        fmt = resource.get("format", "mp3")
        original_name = resource.get("original_filename", "audio_file")
        filename = f"{original_name}.{fmt}"

        cdn_response = http_requests.get(file_url, timeout=30)
        if cdn_response.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not fetch file from storage.")

        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "audio/mpeg"

        return StreamingResponse(
            io.BytesIO(cdn_response.content),
            media_type=mime_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-File-Name": filename,
            }
        )

    except cloudinary.api.NotFound:
        raise HTTPException(status_code=404, detail="No audio files have been uploaded yet.")
    except HTTPException:
        raise
    except cloudinary.api.Error as e:
        raise HTTPException(status_code=502, detail=f"Cloudinary error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
