FROM python:3.10

WORKDIR .

COPY requirements.txt .

RUN pip install celery redis
    #pip install -r requirements.txt

COPY . .

#CMD ["gunicorn", "tmp.py:app", "-b", "0.0.0.0:5000"]
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]