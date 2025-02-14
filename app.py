from flask import Flask, request, jsonify, render_template, send_file, Response
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
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
from flask_cors import CORS


load_dotenv()

app = Flask(__name__)
CORS(app)

app.config['CACHE_TYPE'] = 'simple' 
cache = Cache(app)
app.config['MAX_CONTENT_LENGTH'] = 25*1024*1024
app.config['UPLOAD_BUFFER_SIZE'] = 8192
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per 10 minutes"]
)



# MongoDB Configuration
MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(
    MONGO_URI,
    server_api=ServerApi('1'),
    tls=True,
    tlsAllowInvalidCertificates=True,  # Skip certificate validation
    tlsCAFile=ssl.get_default_verify_paths().cafile  # Explicitly set CA file path
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
@limiter.limit("1 per minute")
def upload_file():
    try:
        data = request.form.to_dict()
        file = request.files.get('file-upload')

        if not file:
            return jsonify({"error": "No file provided"}), 400

        # Validate file type
        valid_types = ['application/pdf']
        if file.content_type not in valid_types:
            return jsonify({"error": "Invalid file type. Only PDF is allowed"}), 400

        # Determine the folder and file name
        folder = "notes" if data["type"].lower() == "notes" else "question_papers"
        file_name = f"{data['title'] if data['type'].lower() == 'notes' else data['course_name']}.pdf"

        # Upload the file to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type="raw",
            public_id = file_name.rsplit('.', 1)[0].strip(),
            overwrite=True
        )

        original_url = upload_result["secure_url"]
        download_url = original_url.replace("upload/", "upload/fl_attachment/")

        # Prepare data for MongoDB
        data["file_url"] = original_url
        data["download_url"] = download_url
        data["tags"] = [tag.strip() for tag in data.get("tags_attachment", "").split(",") if tag.strip()]  # Convert tags to a list

        # Insert into the appropriate MongoDB collection
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
        search_term = request.args.get('search', '').strip().lower()
        college_filter = request.args.get('college', '').strip()
        subject_filter = request.args.get('subject', '').strip()
        code_filter = request.args.get('code', '').strip()

        # Base queries
        notes_query = {}
        questions_query = {}

        # Search logic
        if search_term:
            notes_query["$or"] = [
                {"title": {"$regex": search_term, "$options": "i"}},
                {"college": {"$regex": search_term, "$options": "i"}},
                {"tags": {"$regex": search_term, "$options": "i"}}
            ]
            questions_query["$or"] = [
                {"course_name": {"$regex": search_term, "$options": "i"}},
                {"course_code": {"$regex": search_term, "$options": "i"}},
                {"college": {"$regex": search_term, "$options": "i"}},
                {"trade": {"$regex": search_term, "$options": "i"}}
            ]

        # Filter logic
        if college_filter:
            notes_query["college"] = {"$regex": f"^{college_filter}$", "$options": "i"}
            questions_query["college"] = {"$regex": f"^{college_filter}$", "$options": "i"}

        if subject_filter:
            notes_query["title"] = {"$regex": f"^{subject_filter}$", "$options": "i"}
            questions_query["course_name"] = {"$regex": f"^{subject_filter}$", "$options": "i"}

        if code_filter:
            questions_query["course_code"] = {"$regex": f"^{code_filter}$", "$options": "i"}

        # Fetch documents
        notes = list(notes_collection.find(notes_query, {'_id': 0}))
        questions = list(questions_collection.find(questions_query, {'_id': 0}))

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

@app.route('/view')
def view_file():
    file_url = request.args.get('file_url')
    
    if not file_url:
        return "Missing file URL", 400

    try:
        # Fetch the PDF with headers to prevent Cloudinary blocking it
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(file_url, stream=True, headers=headers, allow_redirects=True)

        if response.status_code != 200:
            return f"Error fetching file: {response.status_code}", 500

        # Stream the PDF response
        return Response(
            response.iter_content(chunk_size=8192),
            content_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=document.pdf"}
        )

    except Exception as e:
        return f"Internal Server Error: {str(e)}", 500


if __name__ == '__main__':
    app.run()