import os
from dotenv import load_dotenv

class Config:
	# 코드 생략
    db_pt = os.environ["DB_PORT"]
    db_id = os.environ["DB_USER"]
    db_pw = os.environ["DB_PASSWORD"]
    db_nm = os.environ["DB_DATABASE"]
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{db_id}:{db_pw}@db:{db_pt}/{db_nm}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False