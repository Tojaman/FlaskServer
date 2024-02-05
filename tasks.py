from celery import Celery
import os, boto3, tempfile, shutil, jsonify, subprocess, re
from dotenv import load_dotenv

load_dotenv()

AWS_DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

celery = Celery('FlaskAiModelServing', broker='redis://127.0.0.1:6379/0', backend='redis://127.0.0.1:6379/0')


@celery.task
def process_uploaded_file(json_data):
    # S3
    """
    body 부분에 아래 형식으로 메시지 전송
    {
        "action": "translate",
        "url": "S3 경로" # 버킷 경로X -> 폴더/파일 이름.wav("original_video/ojtube.wav")
    }
    """

    # RVC
    """
    body 부분에 아래 형식으로 메시지 전송
    {
        "url": "original_video/ojtube.wav"

    }
    """

    result = []

    # s3 연결 및 객체 생성
    s3 = s3_connection()

    # 음성 파일이 저장된 S3 경로
    s3_url = json_data['url']

    # 임시 디렉토리에 파일 저장
    with tempfile.TemporaryDirectory() as temp_dir:
        local_file_dir = os.path.join(temp_dir, 'video.wav')

        # 다운로드
        if s3_get_object(s3, S3_BUCKET, s3_url, local_file_dir):
            result.append("파일 다운 성공")
        else:
            result.append("파일 다운 실패")

        # RVC 변환
        convert_voice_path = execute_voice_conversion(json_data, local_file_dir)

        # RVC 변환 음성 파일 이름 추출
        convert_file_name = os.path.basename(convert_voice_path)

        # 업로드
        convert_file_path_s3 = "convert_voice/" + convert_file_name # 저장할 S3 경로
        if s3_put_object(s3, S3_BUCKET, convert_voice_path, convert_file_path_s3):
            result.append("파일 업로드 성공")
        else:
            result.append("파일 업로드 실패")

        # 임시 디렉토리 삭제
        shutil.rmtree(temp_dir)

        # 임시 디렉토리 삭제 되었는지 확인
        if os.path.exists(local_file_dir):
            result.append(f"임시 디렉토리에 파일이 여전히 존재합니다: {local_file_dir}")
        else:
            result.append("임시 디렉토리의 파일이 삭제되었습니다.")

    return convert_file_path_s3


# S3 연결 및 S3 객체 반환
@celery.task
def s3_connection():
    """
    s3 bucket에 연결
    :return: 연결된 s3 객체
    """
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


@celery.task
# S3에서 파일 다운로드
def s3_get_object(s3, bucket, s3_filepath, local_filepath):
    """
    s3 bucket에서 지정 파일 다운로드
    s3: 연결된 s3 객체(boto3 client)
    bucket: 버킷명
    s3_filepath: 다운 받을 파일의 s3 경로(파일 이름까지)
    local_filepath: 파일이 저장될 local 경로(파일 이름까지)
    성공 시 True, 실패 시 False 반환
    """
    try:
        s3.download_file(bucket, s3_filepath, local_filepath)
        print("s3 file download")
        return True
    except Exception as e:
        print(e)
        return False


# S3에 파일 업로드
@celery.task
def s3_put_object(s3, bucket, local_filepath, s3_filepath):
    """
    s3 bucket에 지정 파일 업로드
    s3: 연결된 s3 객체(boto3 client)
    bucket: 버킷명
    local_filepath: 업로드 할 파일의 local 경로(파일 이름까지)
    s3_filepath: 파일을 업로드 할 s3 경로(파일 이름까지)
    성공 시 True, 실패 시 False 반환
    """
    try:
        s3.upload_file(local_filepath, bucket, s3_filepath)
        print("s3 file upload")
    except Exception as e:
        print(e)
        return False
    return True


@celery.task
def execute_voice_conversion(data, local_file_dir):
    # 설정값을 사용하여 명령어 생성
    command = [
        "python3",
        "RVC_custom/src/main.py",
        "-i", local_file_dir,
        "-dir", data["RVC_DIRNAME"],
        "-p", "0",
        "-pall", "0",
        "-ir", "0.75",
        "-fr", "3",
        "-rms", "0.25",
        "-palgo", "rmvpe",
        "-hop", "64",
        "-pro", "0.33",
        "-mv", "0",
        "-bv", "0",
        "-iv", "0",
        "-rsize", "0.15",
        "-rwet", "0.2",
        "-rdry", "0.8",
        "-rdamp", "0.7",
        "-oformat", "wav"
    ]
    # 명령어 실행
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    # 명령어 실행 결과 반환
    # output = ""
    cover_path = ""
    for line in process.stdout:
        # 정규식을 사용하여 파일 경로 추출
        match = re.search(r'Cover generated at (.+)', line)
        if match:
            cover_path = match.group(1).strip()
            # print(cover_path)  # 파일 경로 출력
        # output += line
        # print(line, end='')

    process.wait()

    return cover_path
