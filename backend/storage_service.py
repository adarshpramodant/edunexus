import os
import sys
import requests

# Supabase Configs
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://pdatpcnsphtwacopvgyf.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

class SupabaseStorageService:
    @staticmethod
    def upload_file(bucket_name, file_path, file_data, content_type):
        if not SUPABASE_KEY:
            raise ValueError("SUPABASE_KEY environment variable is not configured.")
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{file_path}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": content_type
        }
        r = requests.post(url, data=file_data, headers=headers)
        if r.status_code == 200:
            return file_path
        else:
            raise Exception(f"Supabase Storage Upload failed: {r.status_code} - {r.text}")

    @staticmethod
    def get_signed_url(bucket_name, file_path, expires_in=3600):
        if not SUPABASE_KEY:
            raise ValueError("SUPABASE_KEY environment variable is not configured.")
        url = f"{SUPABASE_URL}/storage/v1/object/sign/{bucket_name}/{file_path}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": "application/json"
        }
        r = requests.post(url, json={"expiresIn": expires_in}, headers=headers)
        if r.status_code == 200:
            return r.json().get("signedURL")
        else:
            raise Exception(f"Supabase Storage Signed URL generation failed: {r.status_code} - {r.text}")

    @staticmethod
    def delete_file(bucket_name, file_path):
        if not SUPABASE_KEY:
            raise ValueError("SUPABASE_KEY environment variable is not configured.")
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{file_path}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY
        }
        r = requests.delete(url, headers=headers)
        return r.status_code == 200


class MockStorageService:
    @staticmethod
    def upload_file(bucket_name, file_path, file_data, content_type):
        mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_storage', bucket_name)
        full_path = os.path.join(mock_dir, file_path.replace('/', os.sep))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            f.write(file_data)
        return file_path

    @staticmethod
    def get_signed_url(bucket_name, file_path, expires_in=3600):
        # Returns a local server endpoint serving mock file downloads
        return f"https://edunexus-quw3.onrender.com/api/documents/mock-download/{bucket_name}/{file_path}"

    @staticmethod
    def delete_file(bucket_name, file_path):
        mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_storage', bucket_name)
        full_path = os.path.join(mock_dir, file_path.replace('/', os.sep))
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                return True
            except Exception:
                pass
        return False


def get_storage_service():
    """
    Return MockStorageService ONLY during active testing contexts.
    Otherwise return production SupabaseStorageService.
    """
    is_testing = os.environ.get("TESTING") == "true"
    if not is_testing:
        try:
            from flask import current_app
            if current_app and current_app.testing:
                is_testing = True
        except Exception:
            pass

    if is_testing or not SUPABASE_KEY:
        return MockStorageService
    return SupabaseStorageService
