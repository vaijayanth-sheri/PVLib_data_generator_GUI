FROM python:3.12-slim

# Install system dependencies required for pvlib and scipy
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy the requirements file and install dependencies
COPY --chown=user requirements.txt $HOME/app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the application
COPY --chown=user . $HOME/app

# Expose port 7860 for Hugging Face Spaces
EXPOSE 7860

# Run the FastAPI server on port 7860
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "7860"]
