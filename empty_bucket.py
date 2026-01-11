import boto3
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load environment variables from .env
load_dotenv()

def empty_r2_bucket(bucket_name=None):
    """
    Empties an R2 bucket using pagination to handle large amounts of objects.
    """
    endpoint_url = os.getenv("R2_ENDPOINT_URL")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    default_bucket = os.getenv("R2_BUCKET_NAME")

    bucket = bucket_name or default_bucket

    if not all([endpoint_url, access_key, secret_key, bucket]):
        print("Error: Missing R2 credentials or bucket name in .env file.")
        return

    print(f"--- R2 Bucket Cleanup Tool ---")
    print(f"Endpoint: {endpoint_url}")
    print(f"Target Bucket: {bucket}")
    
    # Initialize S3 client for R2
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto"
    )

    # Safety Confirmation
    confirm = input(f"Are you sure you want to delete ALL objects in '{bucket}'? (y/N): ")
    if confirm.lower() != 'y':
        print("Aborted.")
        return

    print(f"Starting deletion from '{bucket}'...")
    
    deleted_count = 0
    continuation_token = None

    try:
        while True:
            # List objects with pagination
            list_params = {"Bucket": bucket, "MaxKeys": 1000}
            if continuation_token:
                list_params["ContinuationToken"] = continuation_token

            response = s3.list_objects_v2(**list_params)
            objects = response.get("Contents", [])

            if not objects:
                if deleted_count == 0:
                    print("Bucket is already empty.")
                else:
                    print(f"Finished. Total objects deleted: {deleted_count}")
                break

            # Prepare objects for deletion
            delete_list = [{"Key": obj["Key"]} for obj in objects]
            
            # Perform bulk deletion
            s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": delete_list}
            )
            
            batch_size = len(delete_list)
            deleted_count += batch_size
            print(f"Deleted batch of {batch_size} objects (Total: {deleted_count})...")

            # Check for more objects
            if response.get("IsTruncated"):
                continuation_token = response.get("NextContinuationToken")
            else:
                print(f"Success! Total objects deleted: {deleted_count}")
                break

    except ClientError as e:
        print(f"Error connecting to R2: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    import sys
    # Allow passing bucket name as CLI argument
    target = sys.argv[1] if len(sys.argv) > 1 else None
    empty_r2_bucket(target)
