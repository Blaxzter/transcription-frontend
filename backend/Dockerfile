FROM python:3.8-slim-bullseye

WORKDIR /build

# install prerequisites
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
		  libopenblas-dev \
		  libopenmpi-dev \
            openmpi-bin \
            openmpi-common \
		  gfortran \
		  libomp-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

COPY requirements.txt requirements.txt

RUN apt-get update
RUN apt-get -y install ffmpeg

RUN pip3 install --no-cache https://developer.download.nvidia.cn/compute/redist/jp/v511/pytorch/torch-2.0.0+nv23.05-cp38-cp38-linux_aarch64.whl

# Install system dependencies
RUN pip3 install -r requirements.txt

# Copy the rest of app
COPY .env .env
COPY main.py main.py
COPY LangModel.py LangModel.py
COPY transcribe.py transcribe.py 

# touch db.json
RUN touch db.json
RUN mkdir audio_files

# Create new user to run app process as unprivilaged user
CMD ["python3", "main.py"]
