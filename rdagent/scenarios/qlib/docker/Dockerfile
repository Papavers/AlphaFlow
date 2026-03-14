FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime

# For GPU support, please choose the proper tag from https://hub.docker.com/r/pytorch/pytorch/tags

# Use Aliyun mirror for faster apt-get in China
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    apt-get clean && apt-get update && apt-get install -y \
    curl \
    vim \
    git \
    build-essential \
    coreutils \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/microsoft/qlib.git

WORKDIR /workspace/qlib

RUN git fetch && git reset 3e72593b8c985f01979bebcf646658002ac43b00 --hard

RUN python -m pip install --upgrade cython
# Skip editable install, use regular install instead
RUN python -m pip install --no-cache-dir . 2>&1 | grep -v "WARNING" || true

RUN pip install catboost
# Install xgboost with pre-built wheels to avoid compilation issues
RUN pip install --only-binary :all: xgboost || pip install xgboost
RUN pip install scipy==1.11.4
RUN pip install tables

