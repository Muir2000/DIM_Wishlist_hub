// 로컬 디스크에서 프론트엔드 dev 서버를 실행하는 래퍼.
//
// 이 프로젝트는 RaiDrive WebDAV 가상 드라이브(예: Y:)에 있을 수 있는데, 그 경우 Vite 의
// 번들러(esbuild/rollup)가 경로를 접근 불가한 드라이브로 정규화해 dev/build 가 실패한다
// (자세한 내용은 README "개발 환경 주의"). 백엔드(파이썬)는 영향이 없다.
//
// 해결: frontend 를 로컬 디스크(%LOCALAPPDATA%\dimhub-fe, 또는 DIMHUB_FE_DIR)로 동기화한 뒤
//       거기서 `npm run dev` 를 실행한다. 소스/설정은 매 실행 동기화하고, node_modules 는
//       없을 때 1회만 복사한다.
//
// 사용: 저장소 루트에서  `node scripts/dev-local.mjs`
//       (Claude 미리보기 패널의 "frontend" 구성도 이 스크립트를 사용한다.)
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const feSrc = join(here, "..", "frontend");
const dest = process.env.DIMHUB_FE_DIR || join(process.env.LOCALAPPDATA || tmpdir(), "dimhub-fe");

mkdirSync(dest, { recursive: true });

// 1) 소스/설정 동기화 (매 실행, 빠름) — 코드 변경 후 재시작하면 반영됨.
for (const f of ["src", "index.html", "package.json", "vite.config.ts", "tsconfig.json", "tsconfig.node.json"]) {
  const s = join(feSrc, f);
  if (existsSync(s)) cpSync(s, join(dest, f), { recursive: true, force: true });
}

// 2) node_modules: vite / 윈도우 플랫폼 바이너리가 없으면 1회 복사.
const needNM =
  !existsSync(join(dest, "node_modules", ".bin", "vite")) ||
  !existsSync(join(dest, "node_modules", "@rollup", "rollup-win32-x64-msvc")) ||
  !existsSync(join(dest, "node_modules", "@esbuild", "win32-x64"));

if (needNM) {
  console.log("[dev-local] node_modules 를 로컬로 복사 중… (최초 1회, 시간이 걸릴 수 있음)");
  if (process.platform === "win32") {
    const r = spawnSync(
      "robocopy",
      [join(feSrc, "node_modules"), join(dest, "node_modules"), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/MT:16"],
      { stdio: "inherit", shell: false },
    );
    if ((r.status ?? 0) >= 8) {
      console.error("[dev-local] node_modules 복사 실패(robocopy). 수동 확인 필요.");
      process.exit(1);
    }
  } else {
    cpSync(join(feSrc, "node_modules"), join(dest, "node_modules"), { recursive: true });
  }
}

// 3) dev 서버 실행 (로컬 디스크에서).
console.log(`[dev-local] dev 서버 실행: ${dest}`);
const child = spawn("npm", ["run", "dev"], { cwd: dest, stdio: "inherit", shell: true });
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    try { child.kill(); } catch {}
    process.exit();
  });
}
child.on("exit", (code) => process.exit(code ?? 0));
