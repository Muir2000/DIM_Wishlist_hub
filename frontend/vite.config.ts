import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드(FastAPI)는 기본 http://127.0.0.1:8000.
// '/api' 요청을 백엔드로 프록시하여 CORS 없이 개발한다.
export default defineConfig({
  plugins: [react()],
  // 참고(이 개발 머신 한정): 프로젝트가 RaiDrive WebDAV 가상 드라이브(Y:)에 있으면
  // Vite 의 esbuild/rollup 이 경로를 접근 불가한 Z: 로 정규화해 dev/build 가 실패한다.
  // 해결책은 로컬 디스크(C:)로 복사해 실행하는 것. preserveSymlinks 는 일반적으로 무해한
  // 기본값으로 유지한다(WebDAV 문제 자체를 고치지는 못함).
  resolve: { preserveSymlinks: true },
  server: {
    host: true, // 0.0.0.0 바인딩 (127.0.0.1 / ::1 모두 접속 가능)
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
