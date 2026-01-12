"""
S3 Storage Utility.
Uploads generated documentation to S3 and returns presigned URLs.
"""
import os
import boto3
from botocore.exceptions import ClientError


def upload_to_s3(content: str, filename: str, content_type: str) -> str:
    """
    Upload content to S3 and return a presigned URL (valid for 7 days).
    
    Args:
        content: File content as string
        filename: S3 object key (e.g., "{job_id}/index.html")
        content_type: MIME type (e.g., "text/html")
    
    Returns:
        Presigned S3 URL
    
    Raises:
        ValueError: If required env vars are missing
        Exception: If S3 upload fails
    """
    bucket_name = os.environ.get('S3_BUCKET')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    
    print(f"[S3_UPLOAD] Bucket: {bucket_name}, Region: {aws_region}, Key: {filename}")
    
    # Validate required env vars
    if not bucket_name:
        raise ValueError("S3_BUCKET environment variable is not set")
    if not aws_access_key or not aws_secret_key:
        raise ValueError("AWS credentials not configured")
    
    # Initialize S3 client
    session = boto3.Session(
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    s3_client = session.client('s3')
    
    try:
        upload_params = {
            'Bucket': bucket_name,
            'Key': filename,
            'Body': content.encode('utf-8'),
            'ContentType': content_type,
        }
        
        # Try with public-read ACL first
        try:
            upload_params['ACL'] = 'public-read'
            s3_client.put_object(**upload_params)
            print(f"[S3_UPLOAD] Uploaded with ACL='public-read'")
        except ClientError as acl_error:
            # ACLs might be disabled on bucket - upload without ACL
            error_code = acl_error.response.get('Error', {}).get('Code', '')
            if error_code in ['InvalidRequest', 'AccessControlListNotSupported', 'NotSupported']:
                print(f"[S3_UPLOAD] ACL not supported, uploading without ACL")
                upload_params.pop('ACL', None)
                s3_client.put_object(**upload_params)
            else:
                raise
        
        # Generate presigned URL (expires in 7 days)
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': filename},
            ExpiresIn=604800  # 7 days
        )
        print(f"[S3_UPLOAD] Generated presigned URL (expires in 7 days)")
        return url
        
    except ClientError as e:
        raise Exception(f"Failed to upload to S3: {str(e)}")
