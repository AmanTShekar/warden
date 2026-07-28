# Use ROCm-enabled PyTorch base image for native AMD GPU support
FROM rocm/pytorch:rocm6.1.2_ubuntu22.04_py3.10_pytorch_2.1.2

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Semgrep for DiffGuard
RUN pip install semgrep

# Copy dependency requirements
COPY requirements.txt .

# Install Python dependencies (exclude llama-cpp-python for custom build)
RUN sed -i '/llama-cpp-python/d' requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Install llama-cpp-python with ROCm (HIP) acceleration
ENV HIPCXX="$(hipconfig -l)/clang"
ENV HIP_PATH="$(hipconfig -R)"
ENV CMAKE_ARGS="-DGGML_HIPBLAS=on -DCMAKE_C_COMPILER=/opt/rocm/llvm/bin/clang -DCMAKE_CXX_COMPILER=/opt/rocm/llvm/bin/clang++"
ENV FORCE_CMAKE=1
RUN pip install --no-cache-dir llama-cpp-python>=0.2.0

# Copy the rest of the application
COPY . .

# Set environment variables for Warden
ENV WARDEN_MODEL_DIR=/app/models
ENV PYTHONPATH=/app

# Expose port for the Gradio UI
EXPOSE 7860

# Default command launches the UI
CMD ["python", "-m", "warden.cli", "ui"]
