from flask import Flask, request, jsonify, render_template, send_file
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import io
import os
import ssl
import requests


load_dotenv()

app = Flask(__name__)

app.config['CACHE_TYPE'] = 'simple' 
cache = Cache(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per 10 minutes"]
)



# MongoDB Configuration
MONGO_URI = os.getenv('MONGO_URI')

client = MongoClient(
        MONGO_URI, 
        tls=True, 
        tlsCAFile=ssl.get_default_verify_paths().cafile
    )
db = client["paperhub"]
notes_collection = db['notes']
questions_collection = db['questions']



# Cloudinary Configuration
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
@cache.cached(timeout=86400)  # Cache assets for 1 day
def cached_static(filename):
    return send_from_directory('static', filename)

@app.route('/upload', methods=['POST'])
@limiter.limit("5 per minute")  
def upload_file():
    try:
        data = request.form.to_dict()
        file = request.files.get('file-upload')

        FIELD_MAPPING = {
            "course_name": "paper_name",
            "course_code": "paper_code",
            "year": "paper_year",
            "college": "college",
            "trade": "trade",
            "semester": "semester",
            "type": "type"
        }
        data = {FIELD_MAPPING.get(k, k): v for k, v in data.items()}

        if not file:
            return jsonify({"error": "No file provided"}), 400

        valid_types = ['application/pdf', 'image/jpeg', 'image/jpg']
        if file.content_type not in valid_types:
            return jsonify({"error": "Invalid file type. Allowed: .jpg, .jpeg, .pdf"}), 400

        folder = "notes" if data["type"].lower() == "notes" else "question_papers"

        # ✅ Upload PDFs as `raw` files so they are served correctly
        resource_type = "raw" if file.content_type == "application/pdf" else "image"
        upload_result = cloudinary.uploader.upload(file, folder=folder, resource_type=resource_type)

        original_url = upload_result["secure_url"]
        download_url = original_url.replace("upload/", "upload/fl_attachment/")

        data["file_url"] = original_url   # For viewing PDFs
        data["download_url"] = download_url  # For correct downloads

        collection = notes_collection if data["type"].lower() == "notes" else questions_collection
        collection.insert_one(data)

        return jsonify({"message": "Upload successful!", "file_url": data["file_url"], "download_url": data["download_url"]}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/get-metadata', methods=['GET'])
def get_metadata():
    try:
        metadata_collection = db["metadata"]
        colleges = metadata_collection.find_one({"type": "colleges"}, {"_id": 0, "values": 1}) or {"values": []}
        course_names = metadata_collection.find_one({"type": "course_names"}, {"_id": 0, "values": 1}) or {"values": []}
        course_codes = metadata_collection.find_one({"type": "course_codes"}, {"_id": 0, "values": 1}) or {"values": []}

        return jsonify({
            "colleges": colleges["values"],
            "course_names": course_names["values"],
            "course_codes": course_codes["values"]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route('/fetch-documents', methods=['GET'])
def fetch_documents():
    try:
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 20)), 50)  # Max limit = 50 per request
        skip = (page - 1) * limit

        notes = list(notes_collection.find({}, {'_id': 0}).skip(skip).limit(limit))
        questions = list(questions_collection.find({}, {'_id': 0}).skip(skip).limit(limit))

        return jsonify({"notes": notes, "questions": questions}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500




    
@app.route('/get-colleges', methods=['GET'])
def get_colleges():
    try:
        response = requests.get("https://universities.hipolabs.com/search?country=India")
        data = response.json()
        college_names = [univ["name"] for univ in data]
        return jsonify({"colleges": college_names})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/download/<string:file_url>', methods=['GET'])
def download_file(file_url):
    # Fetch the file from Cloudinary for download
    response = cloudinary.utils.download(file_url)
    return send_file(io.BytesIO(response.content), download_name=file_url.split('/')[-1])

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
