/** @type {import('next').NextConfig} */
const nextConfig = {
  // 1차 프런트는 서버 컴포넌트에서 백엔드를 직접 fetch하므로 CORS 불필요.
  // (브라우저 직접 호출이 필요해지면 HIVE-64에서 backend CORSMiddleware로 처리)
  reactStrictMode: true,
};

export default nextConfig;
