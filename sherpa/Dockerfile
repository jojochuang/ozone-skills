# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Force x86_64 base environment for maximum binary compatibility
FROM --platform=linux/amd64 rockylinux:9

LABEL maintainer="Apache Ozone Dev Team"
LABEL description="Standalone build environment for compiling Apache Ozone release binaries"

# Update and install base build/VCS tools
RUN dnf update -y && \
    dnf install -y --allowerasing \
        subversion \
        git \
        pinentry \
        cmake \
        gcc-c++ \
        make \
        patch \
        which \
        gnupg2 \
        tar \
        wget \
        curl && \
    dnf clean all

# Install Eclipse Temurin OpenJDK 8 to avoid JNI detection errors (FindJNI)
RUN mkdir -p /usr/lib/jvm/temurin-8-jdk-amd64 && \
    curl -fsSL https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u412-b08/OpenJDK8U-jdk_x64_linux_hotspot_8u412b08.tar.gz | tar -xz -C /usr/lib/jvm/temurin-8-jdk-amd64 --strip-components=1

# Configure Java Environment Variables exactly as required
ENV JAVA_HOME=/usr/lib/jvm/temurin-8-jdk-amd64
ENV PATH=$JAVA_HOME/bin:$PATH

# Install Apache Maven 3.9.9 (Latest stable Maven 3.x)
RUN mkdir -p /opt && \
    curl -fsSL https://archive.apache.org/dist/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.tar.gz | tar -xz -C /opt && \
    ln -s /opt/apache-maven-3.9.9 /opt/maven

# Configure Maven Environment Variables
ENV M2_HOME=/opt/maven
ENV MAVEN_HOME=/opt/maven
ENV PATH=$MAVEN_HOME/bin:$PATH

# Install Protolock v0.17.0 for backward compatibility protocol checking
RUN curl -fsSL -o /tmp/protolock.tgz https://github.com/nilslice/protolock/releases/download/v0.17.0/protolock.20231219T195034Z.linux-amd64.tgz && \
    tar -xzf /tmp/protolock.tgz -C /usr/local/bin/ && \
    rm -f /tmp/protolock.tgz

# Set default work directory
WORKDIR /workspace

# Print environment summary on build to verify correctness
RUN java -version && mvn -version && protolock --version
