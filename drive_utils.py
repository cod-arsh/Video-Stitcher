import io
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "service_account.json"

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

def find_file_id(service, folder_id, filename):
    query = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None

def find_subfolder_id(service, parent_id, name):
    query = (
        f"'{parent_id}' in parents and name='{name}' "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if not files:
        raise FileNotFoundError(f"Folder '{name}' not found under parent {parent_id}")
    return files[0]["id"]

def download_file(service, file_id, local_path):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(local_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.close()

def upload_file(service, folder_id, local_path, remote_name, mime_type):
    file_metadata = {"name": remote_name, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    existing_id = find_file_id(service, folder_id, remote_name)
    if existing_id:
        file = service.files().update(fileId=existing_id, media_body=media).execute()
    else:
        file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file.get("id")