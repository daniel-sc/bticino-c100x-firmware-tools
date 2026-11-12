FROM ubuntu:24.04
COPY setup-linux.sh /tmp/setup-linux.sh
RUN DEBIAN_FRONTEND=noninteractive bash /tmp/setup-linux.sh && rm /tmp/setup-linux.sh
