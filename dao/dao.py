import pymysql, os

class VideoDao:
    def __init__(self):
        # MySQL 데이터베이스 연결
        self.db = pymysql.connect(host=os.environ.get('DB_HOST'),
                             user=os.environ.get('DB_USER'),
                             password=os.environ.get('DB_PASSWORD'),
                             db=os.environ.get('DB_DATABASE'),
                             charset='utf8')



    # video_id에 해당하는 레코드(행)에 convert_s3_path 값 저장
    def update_video_s3_path(self, video_id, convert_s3_path):
        cursor = self.db.cursor()
        cursor.execute('UPDATE videos SET convert_s3_path = %s WHERE id = %s', (convert_s3_path, video_id))
        self.db.commit()
        cursor.close()

    # video_id에 해당하는 레코드(행)의 original_path를 삭제
    def delete_original_video_s3_path(self, video_id):
        cursor = self.db.cursor()
        cursor.execute('UPDATE videos SET original_s3_path = NULL WHERE id = %s', video_id)
        self.db.commit()
        cursor.close()

    def __del__(self):
        self.db.close()
