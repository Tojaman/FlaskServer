FROM python
WORKDIR .
COPY main.py .
RUN pip install flask-restx, pip install celery, pip install redis
EXPOSE 5000
CMD ["python","main_RVC.py"]