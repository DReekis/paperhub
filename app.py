from flask import Flask, request, jsonify, render_template                                                                                       
from flask_cors import CORS
from pymongo import MongoClient
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# MongoDB Setup
client = MongoClient(os.getenv("MONGO_URI"))        
db = client["student_resources"]
collection = db["resources"]

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
def upload_document():
    data = request.form.to_dict()
    file = request.files['file']
    upload_result = cloudinary.uploader.upload(file)
    data['file_url'] = upload_result['secure_url']
    collection.insert_one(data)
    return jsonify({"message": "Document uploaded successfully!", "file_url": data['file_url']})

if __name__ == '__main__':
    app.run(debug=True)
