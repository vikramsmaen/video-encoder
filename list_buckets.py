import boto3
import os
from dotenv import load_dotenv

load_dotenv()

R2_ENDPOINT_URL = os.getenv('R2_ENDPOINT_URL')
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY')

print(f"Connecting to {R2_ENDPOINT_URL}...")

try:
    s3 = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name='auto'
    )

    response = s3.list_buckets()
    print("Buckets found:")
    for bucket in response['Buckets']:
        print(f"- {bucket['Name']}")

except Exception as e:
    print(f"Error: {e}")
