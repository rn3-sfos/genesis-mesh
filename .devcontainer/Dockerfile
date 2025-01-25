FROM docker.io/ubuntu:rolling
USER root

# Use your own password
RUN echo "ubuntu:password" | chpasswd && \
    apt update && apt dist-upgrade -y && \
    apt install -y python3.12-full python3.12-venv pipx git sudo

USER ubuntu
RUN pipx ensurepath && \
    pipx install hatch