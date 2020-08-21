FROM pytorch/pytorch:1.6.0-cuda10.1-cudnn7-devel
RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get install -y wget
RUN apt-get install -y git
RUN DEBIAN_FRONTEND="noninteractive" apt-get -y install tzdata
RUN apt-get -y install libopencv-dev python3-opencv
RUN pip install opencv-contrib-python
RUN pip install python-dotenv kafka-python
RUN pip install redis
RUN pip install pillow
RUN wget https://raw.githubusercontent.com/csailvision/places365/master/categories_places365.txt
COPY  . .
CMD ["python", "main.py"]
