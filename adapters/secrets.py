import os
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

def get_secret(identifier: str, *, from_aws: bool = False) -> str:
    """
    If from_aws=True, `identifier` is a Secrets Manager ARN or name.
    Otherwise `identifier` is treated as an env var key.
    """
    if not from_aws:
        val = os.getenv(identifier)
        if not val:
            raise RuntimeError(f"Secret {identifier} not found in environment")
        return val

    client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
    try:
        resp = client.get_secret_value(SecretId=identifier)
        if "SecretString" in resp:
            return resp["SecretString"]
        else:
            # binary not expected here
            raise RuntimeError("Binary secret not supported")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Failed to read secret {identifier} from AWS: {e}") from e
