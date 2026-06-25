import { useEffect, useState } from "react";
import { api } from "../api";
import type { ExportResult } from "../api";
import { useWishlist } from "../store";

// 우측 컬럼: 빌드 정보(제목/설명) + 리스트 컴파일(미리보기·다운로드).
export function WishlistPanel() {
  const { rolls, title, description, setTitle, setDescription } = useWishlist();
  const [exp, setExp] = useState<ExportResult | null>(null);

  useEffect(() => {
    if (rolls.length === 0) {
      setExp(null);
      return;
    }
    const t = window.setTimeout(() => {
      api
        .exportList({ title, description, rolls: rolls.map((r) => r.input) })
        .then(setExp)
        .catch(() => setExp(null));
    }, 250);
    return () => window.clearTimeout(t);
  }, [rolls, title, description]);

  function download() {
    if (!exp) return;
    const blob = new Blob([exp.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = exp.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="panel chamfer">
        <div className="panel-title">빌드 정보</div>
        <input
          className="text-input"
          placeholder="이름 (예: 갈망의 칼날 PvE 갓롤)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ marginBottom: 10 }}
        />
        <textarea
          className="text-input"
          rows={2}
          placeholder="설명 (선택)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="panel-title" style={{ margin: 0 }}>리스트 컴파일 ({rolls.length} 롤)</span>
          {exp && <span className="panel-actions" style={{ fontFamily: "var(--font-mono)" }}>{exp.line_count}줄</span>}
        </div>

        {rolls.length === 0 ? (
          <div className="empty">추가된 롤이 없습니다.<br />가운데에서 무기·퍽을 골라 “위시리스트에 추가”를 누르세요.</div>
        ) : (
          <>
            {exp?.warning && <div className="warning-box">⚠ {exp.warning}</div>}
            <div className="code-preview">{exp?.content ?? "컴파일 중…"}</div>
            <button
              className="btn primary"
              style={{ width: "100%", marginTop: 12 }}
              disabled={!exp}
              onClick={download}
            >
              ⬇ .txt 다운로드
            </button>
            <div className="instructions" style={{ marginTop: 14 }}>
              <strong>DIM에 적용</strong> — 설정 → <code>위시 리스트</code> → <code>파일에서 불러오기</code>.
              매칭 롤에 👍, 트래시 롤에 👎. 검색: <code>is:wishlist</code>, <code>wishlistnotes:pvp</code>.
              <br />
              <span className="hint">쉼표는 AND, 같은 열의 여러 퍽은 자동으로 여러 줄로 전개됩니다.</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
