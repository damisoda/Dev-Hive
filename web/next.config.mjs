import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // 서버 컴포넌트/BFF가 백엔드를 내부망으로 fetch하므로 브라우저 CORS는 백엔드에서 처리(HIVE-64).
  reactStrictMode: true,
  // 맥미니 Docker 배포용 — 최소 런타임 이미지(.next/standalone + node server.js).
  output: "standalone",

  // HIVE-64: NEXT_PUBLIC_API_BASE_URL 환경변수로 런타임에 백엔드 API 주소를 주입한다.
  // 로컬 기본값: http://localhost:8000 (page.tsx 내부 폴백으로도 처리)
  // Vercel 배포 시: Vercel 환경변수 설정에서 NEXT_PUBLIC_API_BASE_URL을 Railway/백엔드 URL로 지정.

  webpack: (config) => {
    // @schema/* → ../frontend/src/types/* 경로 alias (tsconfig와 동일하게 맞춤)
    config.resolve.alias["@schema"] = path.resolve(__dirname, "../frontend/src/types");
    return config;
  },
};

export default nextConfig;
