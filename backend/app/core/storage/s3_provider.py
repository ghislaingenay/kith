"""S3-compatible storage provider (AWS S3, MinIO, Cloudflare R2)."""

import asyncio
import io
from collections.abc import AsyncIterator
from typing import Literal

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from core.storage.exceptions import (
    StorageError,
    StorageObjectNotFoundError,
    StoragePermissionError,
)
from core.storage.provider import (
    CompletedPart,
    StorageObjectMetadata,
    StoragePart,
    StorageProvider,
)

_NOT_FOUND_CODES = {"NoSuchKey", "404"}
_PERMISSION_DENIED_CODES = {"AccessDenied", "403"}

_DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024


class S3StorageProvider(StorageProvider):
    """Storage provider for AWS S3 and S3-compatible services (MinIO, R2).

    Credentials are resolved via boto3's standard credential chain (env vars,
    IAM role, core config file) — never passed or hardcoded here. `endpoint_url`
    lets this same implementation target MinIO (local dev) or R2 instead of AWS.

    `presign_endpoint_url` is the host baked into presigned URLs when it
    differs from `endpoint_url` — e.g. MinIO reached as `minio:9000` inside
    Docker but as `localhost:9000` from a browser. SigV4 signs the host, so
    the URL must be signed for the host the client will actually request.
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        public_base_url: str | None = None,
        presign_endpoint_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url
        self._public_base_url = public_base_url
        self._client = self._build_client(endpoint_url)
        # Presigning is local signing (no network call), so a second client
        # for the browser-facing host costs nothing at runtime.
        self._presign_client = (
            self._build_client(presign_endpoint_url)
            if presign_endpoint_url
            else self._client
        )

    def _build_client(self, endpoint_url: str | None):
        return boto3.client(
            "s3",
            region_name=self._region,
            endpoint_url=endpoint_url,
            config=BotoConfig(signature_version="s3v4"),
        )

    async def upload(
        self,
        key: str,
        stream: AsyncIterator[bytes] | bytes,
        metadata: dict[str, str] | None = None,
        *,
        public: bool = False,
        content_type: str | None = None,
    ) -> str:
        body = await self._materialize(stream)
        extra_args: dict = {"Metadata": metadata} if metadata else {}
        if public:
            extra_args["ACL"] = "public-read"
        if content_type:
            extra_args["ContentType"] = content_type
        try:
            await asyncio.to_thread(
                self._client.upload_fileobj,
                body,
                self._bucket,
                key,
                ExtraArgs=extra_args,
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc
        return self._public_url(key) if public else key

    def public_url(self, key: str) -> str:
        return self._public_url(key)

    def _public_url(self, key: str) -> str:
        if self._public_base_url:
            return f"{self._public_base_url.rstrip('/')}/{key}"
        if self._endpoint_url:
            # Path-style — matches MinIO/R2, which this same implementation
            # also targets via a custom `endpoint_url`.
            return f"{self._endpoint_url.rstrip('/')}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

    async def download(self, key: str) -> AsyncIterator[bytes]:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc

        body = response["Body"]
        try:
            while True:
                chunk = await asyncio.to_thread(body.read, _DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc

    async def head(self, key: str) -> StorageObjectMetadata:
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc

        return StorageObjectMetadata(
            size=response["ContentLength"],
            etag=response["ETag"].strip('"'),
            last_modified=response["LastModified"].isoformat(),
            content_type=response.get("ContentType"),
        )

    async def generate_presigned_url(
        self, key: str, method: Literal["GET", "PUT"], ttl: int
    ) -> str:
        client_method = "get_object" if method == "GET" else "put_object"
        try:
            return await asyncio.to_thread(
                self._presign_client.generate_presigned_url,
                ClientMethod=client_method,
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=ttl,
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc

    async def create_multipart_upload(self, key: str) -> str:
        try:
            response = await asyncio.to_thread(
                self._client.create_multipart_upload, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc
        return str(response["UploadId"])

    async def generate_part_upload_url(
        self, key: str, upload_id: str, part_number: int, ttl: int
    ) -> str:
        try:
            return await asyncio.to_thread(
                self._presign_client.generate_presigned_url,
                ClientMethod="upload_part",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=ttl,
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc

    async def list_parts(self, key: str, upload_id: str) -> list[StoragePart]:
        try:
            response = await asyncio.to_thread(
                self._client.list_parts,
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc

        return [
            StoragePart(
                part_number=part["PartNumber"],
                etag=part["ETag"].strip('"'),
                size=part["Size"],
            )
            for part in response.get("Parts", [])
        ]

    async def complete_multipart_upload(
        self, key: str, upload_id: str, parts: list[CompletedPart]
    ) -> str:
        try:
            await asyncio.to_thread(
                self._client.complete_multipart_upload,
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={
                    "Parts": [
                        {"PartNumber": part.part_number, "ETag": part.etag}
                        for part in parts
                    ]
                },
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc
        return key

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.abort_multipart_upload,
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
            )
        except ClientError as exc:
            raise self._translate_error(key, exc) from exc

    @staticmethod
    async def _materialize(stream: AsyncIterator[bytes] | bytes) -> io.BytesIO:
        """Convert a byte stream or raw bytes into a seekable BytesIO buffer.

        If given an asynchronous iterator, all chunks are consumed and aggregated in memory.

        Args:
            stream: The raw binary data as a `bytes` object or an `AsyncIterator`
                yielding `bytes` chunks.

        Returns:
            A seekable `io.BytesIO` instance containing the full byte payload,
            positioned at the start (offset 0).

        Note:
            This method accumulates the entire payload into RAM before returning.
            It is suitable for small-to-medium streams but may cause high memory
            usage for extremely large files.
        """
        if isinstance(stream, bytes):
            return io.BytesIO(stream)
        # Writing into a BytesIO incrementally avoids the extra copy
        buffer = io.BytesIO()
        async for chunk in stream:
            buffer.write(chunk)
        buffer.seek(0)
        return buffer

    @staticmethod
    def _translate_error(key: str, exc: ClientError) -> StorageError:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in _NOT_FOUND_CODES:
            return StorageObjectNotFoundError(key)
        if code in _PERMISSION_DENIED_CODES:
            return StoragePermissionError(key)
        return StorageError(f"S3 operation failed for key {key!r}: {exc}")
