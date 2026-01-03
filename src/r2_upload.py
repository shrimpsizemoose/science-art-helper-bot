import os

import boto3
from botocore.exceptions import ClientError


def is_r2_configured() -> bool:
    required_vars = [
        "R2_ENDPOINT_URL",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_PUBLIC_URL",
    ]
    return all(os.environ.get(var) for var in required_vars)


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )


def upload_to_r2(content: bytes, filename: str, content_type: str = "text/html") -> str:
    client = get_r2_client()
    bucket_name = os.environ["R2_BUCKET_NAME"]
    public_url = os.environ["R2_PUBLIC_URL"].rstrip("/")
    prefix = os.environ.get("R2_UPLOAD_PREFIX", "").strip("/")

    if prefix:
        key = f"{prefix}/{filename}"
    else:
        key = filename

    try:
        client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
    except ClientError:
        raise

    return f"{public_url}/{key}"
