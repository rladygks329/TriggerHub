# EC2 배포 가이드

## 📋 목차
1. [EC2 준비](#1-ec2-준비)
2. [Docker 배포 (권장)](#2-docker-배포-권장)
3. [배포 후 확인](#3-배포-후-확인)
4. [업데이트 방법](#4-업데이트-방법)
5. [문제 해결](#5-문제-해결)

---

## 1. EC2 준비

### 보안 그룹 설정
- **EC2 콘솔** → 보안 그룹 → 인바운드 규칙 추가
- 포트 `8000` (또는 원하는 포트) - HTTP
- 소스: `0.0.0.0/0` (또는 특정 IP만 허용)

### 방화벽 확인 (UFW 사용 시)
```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

---

## 2. Docker 배포 (권장)

### 방법 A: Git을 통한 배포 (가장 간단)

#### 1. 로컬에서 Git에 푸시
```bash
git add .
git commit -m "Deploy ready"
git push origin main
```

#### 2. EC2에서 클론 및 실행
```bash
# EC2 접속 후
cd /home/ubuntu

# 프로젝트 클론
git clone <your-repo-url> TriggerHub
cd TriggerHub

# Docker 설치 (없는 경우)
sudo apt update
sudo apt install docker.io docker-compose -y
sudo systemctl start docker
sudo systemctl enable docker

# .env 파일 생성 (중요!)
nano .env
```

`.env` 파일 내용:
```env
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-ec2-public-ip,your-domain.com

OKX_API_KEY=your-okx-api-key
OKX_SECRET_KEY=your-okx-secret-key
OKX_PASSPHRASE=your-okx-passphrase

WEBHOOK_SECRET=your-webhook-secret
```

**중요**: `DJANGO_ALLOWED_HOSTS`에 EC2 퍼블릭 IP 또는 도메인을 추가하세요.

#### 3. Docker로 실행
```bash
# docker-compose로 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

---

### 방법 B: 파일 직접 업로드 (Git 없이)

#### 1. 로컬에서 압축
```bash
# Windows PowerShell
Compress-Archive -Path . -DestinationPath triggerhub.zip -Exclude .git,venv,__pycache__,db.sqlite3
```

#### 2. EC2로 업로드
```bash
# SCP 사용 (로컬에서 실행)
scp -i your-key.pem triggerhub.zip ubuntu@your-ec2-ip:/home/ubuntu/

# 또는 WinSCP, FileZilla 같은 GUI 도구 사용
```

#### 3. EC2에서 압축 해제 및 실행
```bash
# EC2 접속 후
cd /home/ubuntu
unzip triggerhub.zip -d TriggerHub
cd TriggerHub

# Docker 설치 (없으면)
sudo apt install docker.io docker-compose -y

# .env 파일 생성
nano .env
# (위와 동일한 내용 입력)

# Docker 실행
docker-compose up -d
```

---

### 방법 C: Docker Hub 사용 (고급)

#### 1. 로컬에서 이미지 빌드 및 푸시
```bash
# 이미지 빌드
docker build -t your-dockerhub-username/triggerhub:latest .

# Docker Hub에 로그인
docker login

# 이미지 푸시
docker push your-dockerhub-username/triggerhub:latest
```

#### 2. EC2에서 이미지 풀 및 실행
```bash
# EC2 접속 후
docker pull your-dockerhub-username/triggerhub:latest

# .env 파일 생성
nano .env

# 컨테이너 실행
docker run -d \
  --name triggerhub \
  -p 8000:8000 \
  --env-file .env \
  your-dockerhub-username/triggerhub:latest
```

---

## 3. 배포 후 확인

### 서버 상태 확인
```bash
# 컨테이너 상태
docker ps

# 로그 확인
docker-compose logs -f
# 또는
docker logs -f triggerhub
```

### 웹훅 테스트
```bash
# 로컬에서 테스트
curl -X POST http://your-ec2-ip:8000/webhook/okx/ \
  -H "Content-Type: application/json" \
  -d '{"secret":"your-webhook-secret","symbol":"BTC-USDT-SWAP","side":"buy","size":"1"}'
```

### 보안 그룹 확인
- EC2 콘솔 → 보안 그룹 → 인바운드 규칙
- 포트 `8000` (또는 사용한 포트) 열려있는지 확인

### 자동 재시작
`docker-compose.yml`에 `restart: unless-stopped`가 포함되어 있어서 서버 재부팅 시에도 자동으로 컨테이너가 시작됩니다.

---

## 4. 업데이트 방법

### Git 사용 시
```bash
# EC2에서
cd /home/ubuntu/TriggerHub
git pull
docker-compose down
docker-compose up -d --build
```

### 파일 업로드 시
```bash
# 새 파일 업로드 후
docker-compose down
docker-compose up -d --build
```

---

## 5. 문제 해결

### 포트가 이미 사용 중일 때
```bash
# 포트 사용 중인 프로세스 확인
sudo lsof -i :8000

# 기존 컨테이너 중지
docker-compose down
```

### 로그 확인
```bash
docker-compose logs -f web
```

### 컨테이너 재시작
```bash
docker-compose restart
```

### 컨테이너 완전 재빌드
```bash
docker-compose down
docker-compose up -d --build
```

---

## 주의사항

1. **DEBUG 모드**: 프로덕션에서는 `DJANGO_DEBUG=false`로 설정
2. **HTTPS**: 실제 운영 시 Nginx + Let's Encrypt로 HTTPS 설정 권장
3. **보안**: `.env` 파일은 절대 Git에 커밋하지 말 것 (이미 .gitignore에 포함됨)
4. **타임존**: EC2 인스턴스 타임존이 UTC인지 확인 (OKX API 타임스탬프와 관련)
