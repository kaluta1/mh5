"""
Simple script to call the API endpoint to ensure January round exists.
This can be used when the direct database script can't run.
"""
import requests
import sys
import os

# Get API URL from environment or use default
# You can also set it manually here if needed
API_URL = os.getenv("API_URL", "https://mh5-hbjp.onrender.com")

def main():
    print("=" * 60)
    print("Calling API to ensure January round exists")
    print(f"API URL: {API_URL}")
    print("=" * 60)
    
    try:
        # Call the ensure-january endpoint
        url = f"{API_URL}/api/v1/rounds/ensure-january"
        print(f"\nCalling: {url}")
        
        response = requests.post(url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n[SUCCESS] January round ready:")
            print(f"   - ID: {data.get('id')}")
            print(f"   - Name: {data.get('name')}")
            print(f"   - Status: {data.get('status')}")
        elif response.status_code == 401:
            print("\n[WARNING] Authentication required. The endpoint may need admin access.")
            print("Response:", response.text)
        else:
            print(f"\n[ERROR] HTTP {response.status_code}")
            print("Response:", response.text)
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        print(f"\n[ERROR] Network error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
