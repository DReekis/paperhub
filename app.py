from flask import Flask, request, jsonify, render_template, send_file
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
import io
import os
import ssl


load_dotenv()

app = Flask(__name__)


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

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        print("Received form data:", request.form.to_dict())  # Debugging
        print("Received file:", request.files.get('file-upload'))  # Debugging

        FIELD_MAPPING = {
            "course_name": "paper_name",
            "course_code": "paper_code",
            "year": "paper_year",
            "college": "college",
            "trade": "trade",
            "semester": "semester",
            "type": "type"
        }
        data = {FIELD_MAPPING.get(k, k): v for k, v in request.form.to_dict().items()}
        file = request.files.get('file-upload')

        # Check if file exists
        if not file:
            return jsonify({"error": "No file provided"}), 400

        # Ensure file type is valid
        valid_types = ['application/pdf', 'image/jpeg', 'image/jpg']
        if file.content_type not in valid_types:
            return jsonify({"error": "Invalid file type. Allowed: .jpg, .jpeg, .pdf"}), 400

        # Upload file to Cloudinary
        folder = "notes" if data["type"].lower() == "notes" else "question_papers"
        upload_result = cloudinary.uploader.upload(file, folder=folder)
        data["file_url"] = upload_result["secure_url"]

        # Save document in MongoDB
        collection = notes_collection if data["type"].lower() == "notes" else questions_collection
        collection.insert_one(data)

        return jsonify({"message": "Upload successful!", "file_url": data["file_url"]}), 201

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500



@app.route('/fetch-documents', methods=['GET'])
def fetch_documents():
    try:
        notes = list(notes_collection.find({}, {'_id': 0}))  # Get all notes
        questions = list(questions_collection.find({}, {'_id': 0}))  # Get all questions

        return jsonify({"notes": notes, "questions": questions}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/download/<string:file_url>', methods=['GET'])
def download_file(file_url):
    # Fetch the file from Cloudinary for download
    response = cloudinary.utils.download(file_url)
    return send_file(io.BytesIO(response.content), download_name=file_url.split('/')[-1])

if __name__ == '__main__':
    app.run(debug=True)
