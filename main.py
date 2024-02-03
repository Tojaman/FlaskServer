from flask import Flask, request, render_template, jsonify
import os, boto3
from tasks import process_uploaded_file, celery
# from celery_config import make_celery

app = Flask(__name__)
# celery.conf.update(app.config)


@app.route('/', methods=['GET'])
def index():
    return "hello"

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    body 부분에 아래 형식으로 메시지 전송
    {
        "action": "translate",
        "url": "S3 경로" # 버킷 경로X -> 폴더/파일 이름.wav("original_video/ojtube.wav")
    }
    """
    json_data = request.json

    result = process_uploaded_file.delay(json_data['url']).get()

    return result

if __name__ == '__main__':
    # 업로드 폴더가 없으면 생성
    # if not os.path.exists(UPLOAD_FOLDER):
    #     os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)