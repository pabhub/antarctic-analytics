import os
import sys
import logging
import asyncio
from pathlib import Path
from vercel_blob import put


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        logger.error("BLOB_READ_WRITE_TOKEN environment variable is not set.")
        logger.error("Create a Blob store in your Vercel project, then export this token locally.")
        sys.exit(1)

    # Use the uncompressed DB directly to save CPU time on serverless cold starts. Vercel Blob is fast.
    db_path = Path(__file__).resolve().parent.parent / "aemet_cache.db"
    
    if not db_path.exists():
        logger.error(f"Local DB not found at {db_path}.")
        logger.error("Run the project locally first to build the cache DB, ensuring it has all the data.")
        sys.exit(1)

    logger.info(f"Uploading {db_path} ({os.path.getsize(db_path) / 1024 / 1024:.2f} MB) to Vercel Blob...")
    
    with open(db_path, "rb") as f:
        resp = put(
            pathname="aemet_cache.db",
            body=f.read(),
            options={"access": "public", "addRandomSuffix": False},
            token=token
        )
    
    logger.info("Upload complete!")
    logger.info(resp)

if __name__ == "__main__":
    asyncio.run(main())
