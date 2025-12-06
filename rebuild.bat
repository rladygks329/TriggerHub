@echo off
REM Docker 컨테이너 재빌드 및 재시작 스크립트 (Windows 배치 파일)

echo 🔄 Docker 컨테이너 재빌드 중...
docker-compose down
docker-compose up -d --build

echo ✅ 재빌드 완료!
echo 📋 로그 확인: docker-compose logs -f

pause

