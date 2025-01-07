from flask import Flask, request, jsonify, render_template                                                                                       
from flask_cors import CORS
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# MongoDB Setup
client = MongoClient(os.getenv("MONGO_URI"))  
db = client["paperhub"]      
notes_collection = db["notes"]
questions_collection = db["questions"]

# Cloudinary Setup
cloudinary.config(
     cloud_name=os.getenv("CLOUDINARY_URL").split("@")[-1],
    api_key=os.getenv("CLOUDINARY_URL").split("//")[1].split(":")[0],
    api_secret=os.getenv("CLOUDINARY_URL").split(":")[2].split("@")[0]
)


@app.route("/")
def home():
    return render_template("index.html")

# Routes
@app.route('/resources', methods=['GET'])
def get_resources():
    filters = request.args.to_dict()
    resources = list(collection.find(filters))
    for resource in resources:
        resource["_id"] = str(resource["_id"])
    return jsonify(resources)

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        # Log form data and uploaded file
        print("Received form data:", request.form.to_dict())
        print("Received file:", request.files.get('file'))

        # Extract form data
        data = request.form.to_dict()
        file = request.files.get('file')

        # Validate form fields
        required_fields = ['type', 'paper_name', 'paper_code', 'paper_year', 'college', 'trade', 'semester']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400

        # Validate file presence
        if not file:
            return jsonify({"error": "No file provided"}), 400

        # Validate file type
        valid_types = ['image/jpeg', 'image/jpg', 'application/pdf']
        if file.content_type not in valid_types:
            return jsonify({"error": "Invalid file type. Allowed: .jpg, .jpeg, .pdf"}), 400

        # Determine the Cloudinary folder
        file_type = data['type'].lower()
        folder = "notes" if file_type == "notes" else "question_papers"

        # Upload file to Cloudinary
        print("Uploading file to Cloudinary...")
        upload_result = cloudinary.uploader.upload(file, folder=folder)
        print("Cloudinary upload result:", upload_result)

        # Extract the uploaded file URL and public ID
        file_url = upload_result['secure_url']
        public_id = upload_result['public_id']
        print("Uploaded file URL:", file_url)

        # Save metadata and Cloudinary file info to MongoDB
        data['file_url'] = file_url
        data['public_id'] = public_id
        collection = notes_collection if file_type == "notes" else questions_collection
        collection.insert_one(data)

        return jsonify({"message": "File uploaded successfully!", "file_url": file_url}), 201

    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500





if __name__ == '__main__':
    app.run(debug=True)
