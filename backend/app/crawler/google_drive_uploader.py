from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ACCOUNT_FILE = Path(
    os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        str(BACKEND_ROOT / "config" / "google_service_account.json"),
    )
)
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive",)


def _drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if not SERVICE_ACCOUNT_FILE.exists():
        raise FileNotFoundError(f"Google service account key not found: {SERVICE_ACCOUNT_FILE}")
    if not GOOGLE_DRIVE_FOLDER_ID:
        raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID environment variable is required")

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=GOOGLE_DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def upload_to_drive(file_path: str | Path) -> str:
    from googleapiclient.http import MediaFileUpload

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Upload file not found: {path}")

    service = _drive_service()

    # 1. 부모 폴더의 소유자(Owner) 이메일 조회 시도
    owner_email = None
    try:
        folder_metadata = (
            service.files()
            .get(
                fileId=GOOGLE_DRIVE_FOLDER_ID,
                fields="owners",
                supportsAllDrives=True,
            )
            .execute()
        )
        owners = folder_metadata.get("owners", [])
        if owners:
            owner_email = owners[0].get("emailAddress")
            logger.info("Found parent folder owner: %s", owner_email)
    except Exception as e:
        logger.warning("Failed to fetch parent folder owner metadata: %s", e)

    # 2. 파일 생성 (우선 업로드)
    metadata = {
        "name": path.name,
        "parents": [GOOGLE_DRIVE_FOLDER_ID],
    }
    media = MediaFileUpload(str(path), mimetype="application/json", resumable=True)

    created = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    file_id = created["id"]
    logger.info("Uploaded %s to Google Drive, file_id=%s. Attempting ownership transfer...", path.name, file_id)

    # 3. 소유자 이메일이 조회된 경우, 소유권 이전을 통해 쿼터 차감 대상 변경
    if owner_email:
        try:
            permission_body = {
                "type": "user",
                "role": "owner",
                "emailAddress": owner_email,
            }
            # v3 API에서는 transferOwnership=True를 통해 소유권을 완전 위임
            service.permissions().create(
                fileId=file_id,
                body=permission_body,
                transferOwnership=True,
                supportsAllDrives=True,
            ).execute()
            logger.info("Successfully transferred file ownership to parent folder owner: %s", owner_email)
        except Exception as e:
            logger.warning("Failed to transfer file ownership to %s: %s", owner_email, e)

    return file_id


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    path = sys.argv[1] if len(sys.argv) > 1 else str(BACKEND_ROOT / "data" / "raw" / f"_{__import__('datetime').date.today().strftime('%Y%m%d')}.json")
    fid = upload_to_drive(path)
    print(f"업로드 완료: {fid}")
