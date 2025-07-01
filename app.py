import os
import requests
from bs4 import BeautifulSoup
import re
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Optional: allow frontend apps to call the API
try:
    from flask_cors import CORS
    use_cors = True
except ImportError:
    use_cors = False

# Load environment variables
load_dotenv()
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

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

    endpoint = 'https://api.firecrawl.dev/v1/scrape'
    headers = {
        'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        "url": target_url,
        "formats": ["rawHtml"],
        "onlyMainContent": True,
        "renderPage": True  # Enable full JS rendering
    }

    response = requests.post(endpoint, headers=headers, json=payload)
    print(f"[DEBUG] Firecrawl status: {response.status_code}")
    response.raise_for_status()

    json_data = response.json()
    print(f"[DEBUG] Firecrawl response keys: {list(json_data.keys())}")

    raw_html = json_data.get("rawHtml", "")
    if not raw_html:
        print("[WARN] No 'rawHtml' in Firecrawl response or it is empty.")
        return []

    print(f"[DEBUG] Raw HTML snippet: {raw_html[:500].replace(chr(10), ' ')}")
    return extract_image_urls_from_html(raw_html)

@app.route("/images", methods=["GET"])
def get_images():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing 'url' parameter"}), 400
    try:
        image_urls = fetch_images_from_url(url)
        return jsonify({"images": image_urls})
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

