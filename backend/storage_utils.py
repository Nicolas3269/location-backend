"""
Utilities for handling file storage operations with S3-compatible storage

This module provides helpers to download/upload files from/to S3 storage
(Cloudflare R2 in production, MinIO in development).

Particularly useful for processing PDFs with pyhanko which requires local files.
"""

import logging
import os
import tempfile
from contextlib import contextmanager
from typing import Optional

from django.core.files.base import File
from django.db.models.fields.files import FieldFile

logger = logging.getLogger(__name__)


@contextmanager
def get_local_file_path(field_file: FieldFile, suffix: str = ".pdf"):
    """
    Context manager to download a file from S3 to a temporary local path.

    Downloads the file from S3-compatible storage (R2/MinIO) to /tmp/,
    yields the local path for processing, then cleans up automatically.

    Usage:
        with get_local_file_path(document.pdf) as local_path:
            # Work with local_path (string)
            process_pdf(local_path)

    Args:
        field_file: Django FieldFile instance
        suffix: File suffix for temporary file (default: .pdf)

    Yields:
        str: Path to temporary local file
    """
    if not field_file:
        raise ValueError("FieldFile is empty or None")

    # Download from S3 to temporary file
    logger.info(f"Downloading file from S3: {field_file.name}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        # Read from S3 and write to temp file
        field_file.open("rb")
        tmp.write(field_file.read())
        field_file.close()
        tmp_path = tmp.name

    logger.info(f"Downloaded to temporary file: {tmp_path}")

    try:
        yield tmp_path
    finally:
        # Clean up temporary file
        try:
            os.remove(tmp_path)
            logger.info(f"Cleaned up temporary file: {tmp_path}")
        except OSError as e:
            logger.warning(f"Failed to remove temporary file {tmp_path}: {e}")


def save_file_to_storage(
    field_file: FieldFile,
    local_path: str,
    filename: Optional[str] = None,
    save: bool = True
) -> None:
    """
    Upload a local file to S3 storage (R2/MinIO).

    Args:
        field_file: Django FieldFile instance to save to
        local_path: Path to the local file to upload
        filename: Optional filename (if None, uses existing field_file.name)
        save: Whether to call save() on the model (default: True)
    """
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")

    # Use existing filename if not provided
    if filename is None:
        filename = os.path.basename(field_file.name) if field_file.name else os.path.basename(local_path)

    logger.info(f"Saving file to storage: {filename}")

    with open(local_path, "rb") as f:
        field_file.save(filename, File(f), save=save)

    logger.info(f"File saved successfully: {filename}")


@contextmanager
def process_pdf_with_storage(
    source_field: FieldFile,
    output_suffix: str = "_signed.pdf"
):
    """
    Context manager for processing PDFs from S3 storage (R2/MinIO).

    This is specifically designed for pyhanko signature workflow:
    1. Downloads source PDF from S3 to /tmp/
    2. Provides temporary paths for processing
    3. Yields (source_path, output_path)
    4. Cleans up temporary files after processing

    Usage:
        with process_pdf_with_storage(document.pdf) as (source_path, output_path):
            sign_pdf(source_path, output_path, ...)
            # File is automatically saved back to S3
            document.latest_pdf.save('signed.pdf', File(open(output_path, 'rb')))

    Args:
        source_field: Source FieldFile to process
        output_suffix: Suffix for output file (default: _signed.pdf)

    Yields:
        tuple: (source_path, output_path) - both are local temporary paths
    """
    if not source_field:
        raise ValueError("Source FieldFile is empty or None")

    # Create temporary output file
    base_name = os.path.basename(source_field.name).replace(".pdf", "")
    output_tmp = tempfile.NamedTemporaryFile(
        suffix=output_suffix,
        prefix=f"{base_name}_",
        delete=False
    )
    output_path = output_tmp.name
    output_tmp.close()

    try:
        # Get local source file (downloads from R2 if needed)
        with get_local_file_path(source_field, suffix=".pdf") as source_path:
            logger.info(f"Processing PDF: {source_path} -> {output_path}")
            yield source_path, output_path
    finally:
        # Clean up output temporary file
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
                logger.info(f"Cleaned up output file: {output_path}")
        except OSError as e:
            logger.warning(f"Failed to remove output file {output_path}: {e}")
