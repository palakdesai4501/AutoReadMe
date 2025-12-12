"""
S3 Storage Utility for uploading generated documentation artifacts.
"""

import os
import boto3
from botocore.exceptions import ClientError
from typing import Optional


def upload_to_s3(content: str, filename: str, content_type: str) -> str:
    """
    Upload content to S3 bucket and return the public URL.
    
    Args:
        content: The file content to upload (as string)
        filename: The S3 object key (filename/path)
        content_type: MIME type (e.g., 'text/html', 'application/json')
    
    Returns:
        Public S3 URL of the uploaded object
    
    Raises:
        ValueError: If required environment variables are missing
        ClientError: If S3 upload fails
    """
    bucket_name = os.environ.get('S3_BUCKET')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    
    print(f"[S3_UPLOAD] Bucket: {bucket_name}, Region: {aws_region}, Key: {filename}")
    
    if not bucket_name:
        error_msg = "S3_BUCKET environment variable is not set"
        print(f"[S3_UPLOAD] ERROR: {error_msg}")
        raise ValueError(error_msg)
    
    if not aws_access_key or not aws_secret_key:
        error_msg = "AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY environment variables are not set"
        print(f"[S3_UPLOAD] ERROR: {error_msg}")
        raise ValueError(error_msg)
    
    # Initialize S3 client with explicit region and credentials
    # Use boto3 session to ensure proper configuration
    session = boto3.Session(
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    s3_client = session.client('s3')
    
    try:
        # Upload with proper ContentType so browser renders instead of downloads
        upload_params = {
            'Bucket': bucket_name,
            'Key': filename,
            'Body': content.encode('utf-8'),
            'ContentType': content_type,
        }
        
        # Try to set ACL for public read access
        # If ACLs are disabled, bucket policy must allow public access
        try:
            upload_params['ACL'] = 'public-read'
            s3_client.put_object(**upload_params)
            print(f"[S3_UPLOAD] Uploaded with ACL='public-read'")
        except ClientError as acl_error:
            error_code = acl_error.response.get('Error', {}).get('Code', '')
            # If ACLs are disabled, upload without ACL (requires bucket policy)
            if error_code in ['InvalidRequest', 'AccessControlListNotSupported', 'NotSupported']:
                print(f"[S3_UPLOAD] ACL not supported, uploading without ACL (bucket policy must allow public access)")
                upload_params.pop('ACL', None)
                s3_client.put_object(**upload_params)
            else:
                print(f"[S3_UPLOAD] ACL error: {error_code} - {str(acl_error)}")
                raise
        
        # Generate presigned URL (expires in 7 days) instead of public URL
        # This works even if bucket is private
        try:
            # Generate presigned URL - boto3 handles region automatically
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': filename,
                },
                ExpiresIn=604800  # 7 days in seconds
            )
            print(f"[S3_UPLOAD] Generated presigned URL (expires in 7 days)")
            # Verify URL contains correct region in hostname for non-us-east-1
            if aws_region != 'us-east-1' and f'.s3.{aws_region}.' not in url:
                print(f"[S3_UPLOAD] WARNING: URL may have region mismatch - expected {aws_region} in hostname")
            return url
        except Exception as presign_error:
            print(f"[S3_UPLOAD] ERROR: Failed to generate presigned URL: {str(presign_error)}")
            print(f"[S3_UPLOAD] Error type: {type(presign_error).__name__}")
            import traceback
            print(f"[S3_UPLOAD] Traceback: {traceback.format_exc()}")
            # Re-raise the error so we know what went wrong
            raise Exception(f"Failed to generate presigned URL: {str(presign_error)}")
        
    except ClientError as e:
        raise Exception(f"Failed to upload to S3: {str(e)}")

