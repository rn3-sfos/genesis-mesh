FROM docker.io/ubuntu:latest
USER root
RUN echo "ubuntu:password" | chpasswd
RUN apt update && apt dist-upgrade -y
RUN apt install -y python3.12-full python3.12-venv git sudo libreoffice libmagic-dev poppler-utils
