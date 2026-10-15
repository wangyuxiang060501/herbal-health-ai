# ============================================================================
# 前端镜像：多阶段构建 —— node 打包，nginx 托管静态文件
#
# 构建（在仓库根目录）：
#   docker build -f frontend/Dockerfile -t herb-frontend:latest ./frontend
# ============================================================================
FROM node:22-alpine AS build

WORKDIR /app

# 依赖先行，利用 Docker 层缓存
COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .
RUN npm run build

# ---------------------------- 运行阶段 ----------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
# SPA 路由：刷新 /result/xxx 这类地址不能 404，要回落到 index.html
# 生产环境用 deploy/nginx.conf 挂载覆盖（那份含 /api 反向代理与 HTTPS）
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
