FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI and install dependencies
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI
WORKDIR /ComfyUI
RUN pip install -r requirements.txt

# Install ComfyUI Custom Nodes
RUN git clone https://github.com/kosinkadink/ComfyUI-VideoHelperSuite.git /ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite && \
    cd /ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite && pip install -r requirements.txt && \
    git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git /ComfyUI/custom_nodes/comfyui_controlnet_aux && \
    cd /ComfyUI/custom_nodes/comfyui_controlnet_aux && pip install -r requirements.txt

# Download models
RUN mkdir -p /ComfyUI/models/vae && \
    wget -O /ComfyUI/models/vae/wan_2.1_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors && \
    \
    mkdir -p /ComfyUI/models/diffusion_models && \
    wget -O /ComfyUI/models/diffusion_models/wan2.1_vace_1.3B_fp16.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_vace_1.3B_fp16.safetensors && \
    \
    mkdir -p /ComfyUI/models/loras && \
    wget -O /ComfyUI/models/loras/Wan21_CausVid_bidirect2_T2V_1_3B_lora_rank32.safetensors https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan21_CausVid_bidirect2_T2V_1_3B_lora_rank32.safetensors && \
    \
    mkdir -p /ComfyUI/models/text_encoders && \
    wget -O /ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors && \
    \
    wget -O /ComfyUI/models/loras/wan21_13_r32_S_LN_res_512_000003000.safetensors https://huggingface.co/RyashDev/blue_stickman_wan_21_13/resolve/main/wan21_13_r32_S_LN_res_512_000003000.safetensors && \
    \
    mkdir -p /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/DWPose-TorchScript-BatchSize5 && \
    wget -O /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/DWPose-TorchScript-BatchSize5/dw-ll_ucoco_384_bs5.torchscript.pt https://huggingface.co/hr16/DWPose-TorchScript-BatchSize5/resolve/main/dw-ll_ucoco_384_bs5.torchscript.pt && \
    \
    mkdir -p /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/yolo-nas-fp16 && \
    wget -O /ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/yolo-nas-fp16/yolo_nas_s_fp16.onnx https://huggingface.co/hr16/yolo-nas-fp16/resolve/main/yolo_nas_s_fp16.onnx

# Copy the rest of the files
WORKDIR /
COPY requirements.txt /requirements.txt
RUN pip install -r requirements.txt
COPY rp_handler.py /
COPY oss_stickman_api.json /

# Set the entrypoint
CMD ["python3", "-u", "rp_handler.py"]