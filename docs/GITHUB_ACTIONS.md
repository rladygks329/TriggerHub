# GitHub Actions 자동 배포 설정

## 1. GitHub Secrets 설정

GitHub 저장소 → Settings → Secrets and variables → Actions에서 다음 시크릿을 추가하세요:

### 필수 Secrets

- `EC2_SSH_KEY`: EC2 접속용 SSH 개인키 (전체 내용)
- `EC2_HOST`: EC2 퍼블릭 IP 또는 도메인 (예: `52.62.21.231`)
- `EC2_USER`: EC2 사용자명 (보통 `ubuntu`)
- `DISCORD_WEBHOOK`: Discord 웹훅 URL (배포 알림용)

### SSH 키 생성 및 설정

```bash
# 로컬에서 SSH 키 생성 (없는 경우)
ssh-keygen -t rsa -b 4096 -f ~/.ssh/ec2_deploy_key

# EC2에 공개키 추가
ssh-copy-id -i ~/.ssh/ec2_deploy_key.pub ubuntu@your-ec2-ip

# 또는 EC2에서 직접 추가
cat ~/.ssh/ec2_deploy_key.pub | ssh ubuntu@your-ec2-ip "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

### Discord 웹훅 생성

1. Discord 서버 → 채널 설정 → 연동 → 웹후크
2. 새 웹후크 만들기
3. 웹후크 URL 복사 → GitHub Secrets에 `DISCORD_WEBHOOK`으로 추가

## 2. EC2 사전 설정

EC2에서 프로젝트 디렉토리와 Git 저장소 설정:

```bash
# EC2 접속 후
cd ~/opt  # 또는 원하는 경로
git clone <your-repo-url> TriggerHub
cd TriggerHub

# .env 파일 생성
nano .env
# (필요한 환경변수 입력)

# Docker 실행 (최초 1회)
docker-compose up -d
```

## 3. 자동 배포 동작

### 트리거

- `main` 브랜치에 push할 때 자동 배포
- GitHub Actions 탭에서 수동 실행 가능 (workflow_dispatch)

### 배포 프로세스

1. 코드 체크아웃
2. SSH로 EC2 접속
3. Git pull (최신 코드 가져오기)
4. Docker 컨테이너 재빌드 및 재시작
5. Health check 확인
6. Discord 알림 전송

## 4. 배포 확인

### GitHub Actions 로그

- GitHub 저장소 → Actions 탭에서 배포 상태 확인

### EC2에서 확인

```bash
# 컨테이너 상태
docker ps

# 로그 확인
docker-compose logs -f

# Health check
curl http://localhost:8000/health/
```

## 5. 문제 해결

### SSH 연결 실패

- `EC2_SSH_KEY`가 올바른지 확인
- EC2 보안 그룹에서 포트 22가 열려있는지 확인
- SSH 키 권한 확인: `chmod 600 ~/.ssh/deploy_key`

### 배포 실패

- GitHub Actions 로그 확인
- EC2에서 수동으로 `git pull` 및 `docker-compose up -d --build` 실행
- `.env` 파일이 올바른지 확인

### Discord 알림이 안 오는 경우

- `DISCORD_WEBHOOK` 시크릿이 올바른지 확인
- Discord 웹훅이 활성화되어 있는지 확인

