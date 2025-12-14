#!/bin/bash
# Docker 컨테이너 재빌드 및 재시작 스크립트

echo "🔄 Docker 컨테이너 재빌드 중..."

# 로그 파일 백업 (서버 재시작 전)
if [ -d "logs" ]; then
    TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
    BACKUP_DIR="logs/backup"
    mkdir -p "$BACKUP_DIR"
    
    # 현재 로그 파일들을 타임스탬프와 함께 백업
    for log_file in logs/*.log; do
        if [ -f "$log_file" ]; then
            filename=$(basename "$log_file" .log)
            backup_file="$BACKUP_DIR/${filename}-${TIMESTAMP}.log"
            cp "$log_file" "$backup_file"
            echo "📦 로그 백업: $(basename "$log_file") → $(basename "$backup_file")"
        fi
    done
    
    # 오래된 백업 파일 정리 (30일 이상 된 파일 삭제)
    find "$BACKUP_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null
    echo "🗑️  오래된 백업 파일 정리 완료 (30일 이상)"
fi

docker-compose down
docker-compose up -d --build

echo "✅ 재빌드 완료!"
echo "📋 로그 확인: docker-compose logs -f"
echo "📁 로그 파일: tail -f logs/app.log"
echo "📁 웹훅 로그: tail -f logs/webhook.log"
echo "📁 OKX 로그: tail -f logs/okx.log"

