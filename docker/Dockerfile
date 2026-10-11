# Образ с инструментами для разборки/сборки прошивки Tempotec V3 Analog.
# Всё, что нужно сборке: 7z (p7zip), ubireader (ubi_reader), mkfs.ubifs
# (mtd-utils), genisoimage, python3 (скрипты tools/*.py), diff (make.sh verify).
#
# Воспроизводимость: база закреплена по digest, ubireader — по версии.
# Собрать и убедиться, что внутри нет ничего лишнего:
#     docker build -t tempotec-fw-tools docker
#     ./docker/fw.sh bash -c 'python3 -V; pip3 show ubi-reader | head -2; 7z i | head -3'
FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        mtd-utils \
        genisoimage \
        radare2 \
        python3 \
        python3-pip \
        python3-lzo \
        python3-pyelftools \
        python3-capstone \
        binutils \
        file \
        less \
        vim-common \
        p7zip-full \
        cpio \
        squashfs-tools \
        patch \
        ca-certificates \
    && pip3 install --break-system-packages --no-cache-dir ubi_reader==0.8.16 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /work
