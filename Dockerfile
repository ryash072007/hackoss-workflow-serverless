FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI and install core dependencies
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI
WORKDIR /ComfyUI
RUN pip install --no-cache-dir -r requirements.txt

# Install ComfyUI Custom Nodes (Chained to prevent layer bloat)
RUN git clone https://github.com/kosinkadink/ComfyUI-VideoHelperSuite.git /ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite && \
    pip install --no-cache-dir -r /ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt && \
    git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git /ComfyUI/custom_nodes/comfyui_controlnet_aux && \
    pip install --no-cache-dir -r /ComfyUI/custom_nodes/comfyui_controlnet_aux/requirements.txt

# Create necessary model directories inside the container
RUN mkdir -p /ComfyUI/models/vae \
             /ComfyUI/models/diffusion_models \
             /ComfyUI/models/loras \
             /ComfyUI/models/text_encoders \
             /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/DWPose-TorchScript-BatchSize5 \
             /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/yolo-nas-fp16

# COPY local models into the container image
COPY models/vae/ /ComfyUI/models/vae/
COPY models/diffusion_models/ /ComfyUI/models/diffusion_models/
COPY models/loras/ /ComfyUI/models/loras/
COPY models/text_encoders/ /ComfyUI/models/text_encoders/
COPY models/controlnet_aux_ckpts/DWPose-TorchScript-BatchSize5/ /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/DWPose-TorchScript-BatchSize5/
COPY models/controlnet_aux_ckpts/yolo-nas-fp16/ /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/yolo-nas-fp16/

# Copy handler configuration and entrypoint files
WORKDIR /
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY rp_handler.py /
COPY oss_stickman_api.json /
COPY tpose_stickman.png /ComfyUI/input/tpose_stickman.png

# Set the entrypoint
CMD ["python3", "-u", "rp_handler.py"]