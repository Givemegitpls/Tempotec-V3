FROM ubuntu:24.04

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
    && pip3 install --break-system-packages --no-cache-dir ubi_reader \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /work
