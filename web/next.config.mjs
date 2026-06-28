/** @type {import('next').NextConfig} */
const nextConfig = {
  // 서버 컴포넌트/BFF가 백엔드를 내부망으로 fetch하므로 브라우저 CORS 불필요.
  reactStrictMode: true,
  // 맥미니 Docker 배포용 — 최소 런타임 이미지(.next/standalone + node server.js).
  output: "standalone",
};

export default nextConfig;
