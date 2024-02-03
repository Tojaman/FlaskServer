from flask import Flask
from tasks import add

app = Flask(__name__)

@app.route('/')
def home():
    result = add.delay(4, 4)
    return f"Task ID: {result.id}"