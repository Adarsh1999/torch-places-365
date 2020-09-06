FROM pytorch/pytorch:1.6.0-cuda10.1-cudnn7-devel
RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get install -y wget
RUN apt-get install -y git
RUN DEBIAN_FRONTEND="noninteractive" apt-get -y install tzdata
RUN apt-get -y install libopencv-dev python3-opencv
COPY  . .
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
