#!/usr/bin/env bash
# ============================================================================
# 6.3.3 首次申请 Let's Encrypt 证书（HTTP-01 校验）
#
# 用法：
#   ./deploy/init-ssl.sh your.domain.com your@email.com
#
# 前置：
#   - 域名 A 记录已指向本机，且 80 端口可访问（校验收明文 HTTP）
#   - docker-compose.prod.yml 中的 frontend 服务已启动
#   - 中国大陆服务器需先完成 ICP 备案，否则 80/443 会被拦截（6.3.4）
#
# 申请成功后执行 `docker compose -f docker-compose.prod.yml restart frontend`
# 让 Nginx 加载新证书。
# ============================================================================
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "用法: $0 <域名> <邮箱>"
  echo "示例: $0 herb.example.com me@example.com"
  exit 1
fi

echo "[1/3] 渲染 Nginx 配置中的域名占位符"
CONF="deploy/nginx.conf"
if grep -q '\${DOMAIN}' "$CONF"; then
  sed -i "s/\${DOMAIN}/$DOMAIN/g" "$CONF"
  echo "      已把 $CONF 中的 \${DOMAIN} 替换为 $DOMAIN"
else
  echo "      $CONF 中已无占位符，跳过"
fi

echo "[2/3] 申请证书（HTTP-01，需要 80 端口可达）"
docker run --rm \
  -v herb-certbot-webroot:/var/www/certbot \
  -v herb-certbot-certs:/etc/letsencrypt \
  certbot/certbot:latest certonly \
  --webroot --webroot-path /var/www/certbot \
  --email "$EMAIL" --agree-tos --no-eff-email \
  -d "$DOMAIN"

echo "[3/3] 重载 Nginx"
docker exec herb-frontend nginx -t && docker exec herb-frontend nginx -s reload

echo
echo "[OK] 证书已签发。访问 https://$DOMAIN 验证，并用 SSL Labs 检查配置："
echo "     https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
echo
echo "注意：证书 90 天过期，certbot 容器会自动续期；"
echo "      可用 'docker exec herb-certbot certbot certificates' 查看状态。"
