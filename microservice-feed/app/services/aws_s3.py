"""
AWS S3 Service for File Storage
Handles upload, download, and deletion of media files
"""
import boto3
from botocore.exceptions import ClientError
from typing import Optional, BinaryIO
import logging
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION
)


class S3Service:
    """Service for AWS S3 operations"""
    
    def __init__(self):
        self.bucket_name = settings.AWS_S3_BUCKET
        self.region = settings.AWS_REGION
    
    def upload_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Upload a file to S3
        
        Args:
            file_obj: File-like object to upload
            key: S3 object key (path)
            content_type: MIME type of the file
            metadata: Optional metadata dict
        
        Returns:
            S3 object URL
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            if metadata:
                extra_args['Metadata'] = metadata
            
            s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                key,
                ExtraArgs=extra_args
            )
            
            url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"
            logger.info(f"✅ File uploaded to S3: {key}")
            return url
        
        except ClientError as e:
            logger.error(f"❌ S3 upload error: {e}")
            raise Exception(f"Failed to upload file to S3: {str(e)}")
    
    def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate a presigned URL for temporary access
        
        Args:
            key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            Presigned URL
        """
        try:
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"❌ S3 presigned URL error: {e}")
            raise Exception(f"Failed to generate presigned URL: {str(e)}")
    
    def delete_file(self, key: str) -> bool:
        """
        Delete a file from S3
        
        Args:
            key: S3 object key
        
        Returns:
            True if successful
        """
        try:
            s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"✅ File deleted from S3: {key}")
            return True
        except ClientError as e:
            logger.error(f"❌ S3 delete error: {e}")
            return False
    
    def file_exists(self, key: str) -> bool:
        """
        Check if a file exists in S3
        
        Args:
            key: S3 object key
        
        Returns:
            True if file exists
        """
        try:
            s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError:
            return False


# Global S3 service instance
s3_service = S3Service()
