# 1. Base Image
FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# 2. System Dependencies Layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    python3-pip \
    git \
    ffmpeg \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 3. Python Environment Setup Layer
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && pip install --upgrade pip

# 4. Core Heavyweight Layer: PyTorch (Isolated so it caches permanently)
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu124 \
    torch torchvision torchaudio

# 5. Core Application Source Layer
WORKDIR /ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git .

# 6. Core Application Dependencies Layer
RUN pip install --no-cache-dir -r requirements.txt

# 7. Custom Node 1: VideoHelperSuite Source & Install
RUN git clone https://github.com/kosinkadink/ComfyUI-VideoHelperSuite.git ./custom_nodes/ComfyUI-VideoHelperSuite
RUN pip install --no-cache-dir -r ./custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt

# 8. Custom Node 2: ControlNet Aux Source, Symlink Setup, and Installation
RUN git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git ./custom_nodes/comfyui_controlnet_aux

# Create the deep directory structure inside the extension path
RUN mkdir -p ./custom_nodes/comfyui_controlnet_aux/ckpts/hr16

# Link the internal extension checkpoint folder directly to the mounted Network Volume target
RUN ln -s /runpod-volume/controlnet_ckpts/DWPose-TorchScript-BatchSize5 ./custom_nodes/comfyui_controlnet_aux/ckpts/hr16/DWPose-TorchScript-BatchSize5 && \
    ln -s /runpod-volume/controlnet_ckpts/yolo-nas-fp16 ./custom_nodes/comfyui_controlnet_aux/ckpts/hr16/yolo-nas-fp16

# Install Node requirements
RUN pip install --no-cache-dir -r ./custom_nodes/comfyui_controlnet_aux/requirements.txt

# 9. Serverless Configuration & Handler Code Layers
COPY requirements.txt /rp_requirements.txt
RUN pip install --no-cache-dir -r /rp_requirements.txt

COPY extra_model_paths.yaml ./extra_model_paths.yaml
COPY tpose_stickman.png ./input/tpose_stickman.png
COPY rp_handler.py /rp_handler.py
COPY oss_stickman_api.json /oss_stickman_api.json

WORKDIR /

CMD ["python3", "-u", "rp_handler.py"]