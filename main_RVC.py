from flask import Flask, request, render_template, jsonify
import os

app = Flask(__name__)

# 업로드된 파일을 저장할 폴더 설정
UPLOAD_FOLDER = './RVC_custon/original_voice'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 업로드된 파일의 확장자 제한 설정 (여기서는 .wav 파일만 허용)
ALLOWED_EXTENSIONS = {'wav', 'mp3'}

# 허용된 확장자인지 확인하는 함수
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # return render_template('index.html')
    return render_template('rvc_option.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    # 업로드된 파일을 처리
    if 'file' not in request.files:
        return "파일이 없습니다."

    file = request.files['file']

    if file.filename == '':
        return "파일을 선택해주세요."

    if file and allowed_file(file.filename):
        # 파일 저장
        filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filename)
        return '파일 업로드 성공!'

    return '허용된 파일 형식이 아닙니다.'


@app.route('/execute_voice_conversion', methods=['POST'])
def execute_voice_conversion():
    # HTML 폼에서 전송된 데이터를 가져옴
    data = request.json

    # 설정값을 사용하여 명령어 생성
    command = [
        "python",
        "src/main_RVC.py",
        "-i", data["SONG_INPUT"],
        "-dir", data["RVC_DIRNAME"],
        "-p", str(data["PITCH_CHANGE"]),
        "-pall", str(data["PITCH_CHANGE_ALL"]),
        "-ir", str(data["INDEX_RATE"]),
        "-fr", str(data["FILTER_RADIUS"]),
        "-rms", str(data["REMIX_MIX_RATE"]),
        "-palgo", data["PITCH_DETECTION_ALGO"],
        "-hop", str(data["CREPE_HOP_LENGTH"]),
        "-pro", str(data["PROTECT"]),
        "-mv", str(data["MAIN_VOL"]),
        "-bv", str(data["BACKUP_VOL"]),
        "-iv", str(data["INST_VOL"]),
        "-rsize", str(data["REVERB_SIZE"]),
        "-rwet", str(data["REVERB_WETNESS"]),
        "-rdry", str(data["REVERB_DRYNESS"]),
        "-rdamp", str(data["REVERB_DAMPING"]),
        "-oformat", data["OUTPUT_FORMAT"]
    ]

    # 명령어 실행
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    # 명령어 실행 결과 반환
    output = ""
    for line in process.stdout:
        output += line

    return jsonify({"result": output})

if __name__ == '__main__':
    # 업로드 폴더가 없으면 생성
    # if not os.path.exists(UPLOAD_FOLDER):
    #     os.makedirs(UPLOAD_FOLDER)

    app.run(debug=True)
