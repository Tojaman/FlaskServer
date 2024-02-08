from flask import Flask, request
from tasks import process_uploaded_file
# from flask_sqlalchemy import SQLAlchemy
from config import Config
import pymysql, os
from dao.dao import VideoDao

# swagger
from flask_restx import Api, Resource, fields

app = Flask(__name__)
# app.config.from_object(Config)
# db = SQLAlchemy(app)

# swagger
api = Api(app, version='1.0', title='Flask API 문서', description='Swagger 문서', doc="/api-docs")

# 네임스페이스 생성과 동시에 등록(flask_restx)
ai_serving_api = api.namespace('convert', description='음성 변환 API')

upload_model = api.model('UploadModel', {
    'url': fields.String(required=True, description='S3 경로', help='S3 경로는 필수'),
    'RVC_model': fields.String(required=True, description='rvc 모델 이름', help='모델 이름은 필수')
})



@ai_serving_api.route('')
class ConvertVoice(Resource):
    @ai_serving_api.expect(upload_model)
    def post(self):
        """
        body 메시지 예시
        {
            "url": "original_video/ojtube.wav",
            "RVC_model": "Elonmusk"
        }
        """
        json_data = request.json
        # file_data = request.files['url']
        # json_data = request.form['RVC_model']

        # 파일 데이터 처리 (여기서는 파일을 저장하는 것으로 예시)
        # file_path = './original_video/' + file_data.filename
        # print(file_path)
        # file_data.save(file_path)

        # celery 비동기 처리
        convert_file_path_s3 = process_uploaded_file.delay(json_data).get()
        # result = process_uploaded_file.delay(file_path, json_data).get()

        # Spring에서 보낸 Video 테이블의 id
        video_id = request.json['video_id']

        # DB의 vidoes 테이블의 id가 일치하는 레코드(행)를 찾아서 s3 경로 저장
        VideoDao().update_video_s3_path(video_id, convert_file_path_s3)

        return convert_file_path_s3
        # return "안녕"

if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)


# @app.route('/upload', methods=['POST'])
# def upload_file():
#     """
#     body 부분에 아래 형식으로 메시지 전송
#     {
#         "action": "translate",
#         "url": "S3 경로" # 버킷 경로X -> 폴더/파일 이름.wav("original_video/ojtube.wav")
#     }
#     """
#     json_data = request.json
#
#     # celery 비동기 처리
#     result = process_uploaded_file.delay(json_data).get()
#
#     return result
