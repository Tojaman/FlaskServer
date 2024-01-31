from flask import Flask, request, render_template, jsonify
import os, boto3
from dotenv import load_dotenv

AWS_DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

app = Flask(__name__)

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

    # 프론트로부터 음성 변환 요청을 받았다면( celery에서 처리할 예정 )
    if json_data['action'] == 'convert':

        # s3 연결 및 객체 생성
        s3 = s3_connection()

        # 음성 파일이 저장된 S3 경로
        s3_url = json_data['url']

        # 음성 파일을 저장할 경로
        file_dir = 'video/video.wav'

        # S3에서 이미지 다운로드
        if s3_get_object(s3, S3_BUCKET, s3_url, file_dir):
            return "파일 다운 성공"
        else:
            return "파일 다운 안됐는데요 ?"

        # S3에 파일 업로드
        original_file_path = "./video/video.wav"
        convert_file_path_s3 = "convert_voice/ojtube.wav"
        if s3_put_object(s3, S3_BUCKET, original_file_path, convert_file_path_s3):
            return "파일 업로드 성공"
        else:
            return "파일 업로드 실패"


# S3 연결 및 S3 객체 반환
def s3_connection():
    '''
    s3 bucket에 연결
    :return: 연결된 s3 객체
    '''
    try:
        s3 = boto3.client(
            service_name='s3',
            region_name=AWS_DEFAULT_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        print("S3 bucket connected!")
        return s3
    except Exception as e:
        print(e)
        raise

# S3에서 파일 다운로드
def s3_get_object(s3, bucket, s3_filepath, local_filepath):
    '''
    s3 bucket에서 지정 파일 다운로드
    s3: 연결된 s3 객체(boto3 client)
    bucket: 버킷명
    s3_filepath: 다운 받을 파일의 s3 경로(파일 이름까지)
    local_filepath: 파일이 저장될 local 경로(파일 이름까지)
    성공 시 True, 실패 시 False 반환
    '''
    try:
        s3.download_file(bucket, s3_filepath, local_filepath)
    except Exception as e:
        print(e)
        return False
    return True

# S3에 파일 업로드
def s3_put_object(s3, bucket, local_filepath, s3_filepath):
    '''
    s3 bucket에 지정 파일 업로드
    s3: 연결된 s3 객체(boto3 client)
    bucket: 버킷명
    local_filepath: 업로드 할 파일의 local 경로(파일 이름까지)
    s3_filepath: 파일을 업로드 할 s3 경로(파일 이름까지)
    성공 시 True, 실패 시 False 반환
    '''
    try:
        s3.upload_file(local_filepath, bucket, s3_filepath)
    except Exception as e:
        print(e)
        return False
    return True

if __name__ == '__main__':
    # 업로드 폴더가 없으면 생성
    # if not os.path.exists(UPLOAD_FOLDER):
    #     os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)