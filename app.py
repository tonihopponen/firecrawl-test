import os
import requests
from bs4 import BeautifulSoup
import re
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import openai
import base64

# Optional: allow frontend apps to call the API
try:
    from flask_cors import CORS
    use_cors = True
except ImportError:
    use_cors = False

# Load environment variables
load_dotenv()
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Debug API keys
if not FIRECRAWL_API_KEY:
    print("[ERROR] FIRECRAWL_API_KEY not found in environment variables!")
    print("[ERROR] Please create a .env file with: FIRECRAWL_API_KEY=your_api_key_here")
    print("[ERROR] Or set the environment variable: export FIRECRAWL_API_KEY=your_api_key_here")
else:
    print(f"[INFO] Firecrawl API Key found: {FIRECRAWL_API_KEY[:10]}...")
if not OPENAI_API_KEY:
    print("[ERROR] OPENAI_API_KEY not found in environment variables!")
    print("[ERROR] Please create a .env file with: OPENAI_API_KEY=your_openai_api_key_here")
    print("[ERROR] Or set the environment variable: export OPENAI_API_KEY=your_openai_api_key_here")
else:
    print(f"[INFO] OpenAI API Key found: {OPENAI_API_KEY[:10]}...")

openai.api_key = OPENAI_API_KEY

app = Flask(__name__)
if use_cors:
    CORS(app)

def extract_image_urls_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    image_urls = set()

    # <img src="..."> or <img data-src="...">
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src')
        if src:
            image_urls.add(src)

    # <source srcset="...">
    for source in soup.find_all('source'):
        srcset = source.get('srcset')
        if srcset:
            for src in srcset.split(','):
                url = src.strip().split(' ')[0]
                image_urls.add(url)

    # Inline background-image URLs
    for tag in soup.find_all(style=True):
        matches = re.findall(r'url\((.*?)\)', tag['style'])
        for match in matches:
            cleaned = match.strip('\'"')
            image_urls.add(cleaned)

    # <meta property="og:image">
    for meta in soup.find_all('meta', property='og:image'):
        content = meta.get('content')
        if content:
            image_urls.add(content)

    print(f"[INFO] Extracted {len(image_urls)} image URLs")
    return list(image_urls)

def fetch_images_from_url(target_url):
    print(f"[INFO] Requesting Firecrawl scrape for URL: {target_url}")

    # Check if API key is available
    if not FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY is not set. Please check your .env file or environment variables.")

    endpoint = 'https://api.firecrawl.dev/v1/scrape'
    headers = {
        'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        "url": target_url,
        "formats": ["rawHtml"],
        "onlyMainContent": True
    }

    print(f"[DEBUG] Request payload: {payload}")
    print(f"[DEBUG] Headers (without API key): {dict(headers, Authorization='Bearer ***')}")

    response = requests.post(endpoint, headers=headers, json=payload)
    print(f"[DEBUG] Firecrawl status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"[ERROR] Response content: {response.text}")
        print(f"[ERROR] Response headers: {dict(response.headers)}")
    
    response.raise_for_status()

    json_data = response.json()
    print(f"[DEBUG] Firecrawl response keys: {list(json_data.keys())}")

    # Check if the response has the expected structure
    if not json_data.get("success"):
        print(f"[ERROR] Firecrawl request failed: {json_data}")
        return []
    
    # The HTML content is nested in the data object
    data = json_data.get("data", {})
    print(f"[DEBUG] Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
    
    raw_html = data.get("rawHtml", "")
    if not raw_html:
        print("[WARN] No 'rawHtml' in Firecrawl response data or it is empty.")
        print(f"[DEBUG] Available data: {data}")
        return []

    print(f"[DEBUG] Raw HTML snippet: {raw_html[:500].replace(chr(10), ' ')}")
    return extract_image_urls_from_html(raw_html)

# Function to get a short description of an image using OpenAI Vision
def describe_image_with_openai(image_url):
    try:
        # Skip SVGs, data URLs, and other unsupported formats
        unsupported_exts = ('.svg', '.ico', '.bmp', '.tiff')
        if (
            image_url.lower().endswith(unsupported_exts)
            or image_url.startswith('data:image/svg+xml')
            or image_url.startswith('data:')
        ):
            print(f"[WARN] Skipping unsupported image format: {image_url}")
            return "Not a supported image format"
        response = openai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            max_tokens=100
        )
        desc = response.choices[0].message.content.strip()
        return desc
    except Exception as e:
        print(f"[ERROR] OpenAI Vision error for {image_url}: {e}")
        return "Description unavailable"

@app.route("/images", methods=["GET"])
def get_images():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing 'url' parameter"}), 400
    try:
        image_urls = fetch_images_from_url(url)
        # Limit to first two images
        image_urls = image_urls[:2]
        results = []
        for img_url in image_urls:
            desc = describe_image_with_openai(img_url)
            results.append({"url": img_url, "description": desc})
        return jsonify({"images": results})
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

