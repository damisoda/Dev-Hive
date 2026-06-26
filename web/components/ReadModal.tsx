"use client";

import { useEffect, useState } from "react";
import { SYNTH_BODY_LABELS } from "@/lib/viewmodel";

type Synth = Record<string, unknown> & {
  one_liner?: string;
  key_takeaways?: string[];
};

// '읽기' → 현재 페이지 위에 모달(오버레이 카드)로 재가공본을 띄운다. 이동 아님.
// 열 때 BFF /api/read 1회: 재가공본(캐시 우선) + 로그인 시 읽음 처리.
export function ReadModal({
  contentId,
  title,
  url,
  loggedIn,
  titleKo,
}: {
  contentId: number;
  title: string;
  url?: string | null;
  loggedIn: boolean;
  titleKo?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [synth, setSynth] = useState<Synth | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [synthPending, setSynthPending] = useState(false);
  const [levelUp, setLevelUp] = useState<string | null>(null);
  const [koOpen, setKoOpen] = useState(false);

  // 영문 제목 + 번역 토글(HIVE-66) — title_ko가 있고 원문과 다를 때만(피드 카드와 동일 판단).
  const ko = titleKo?.trim();
  const showTitleToggle = Boolean(ko && ko !== title.trim());

  async function load() {
    setLoading(true);
    setSynthPending(false);
    setErr(null);
    try {
      const res = await fetch("/api/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content_id: contentId }),
      });
      const data = await res.json();
      if (!res.ok) setErr(data.error ?? "재가공본을 불러오지 못했어요.");
      else if (data.synthesis) {
        setSynth(data.synthesis as Synth);
        if (data.leveled_up && data.new_level) setLevelUp(data.new_level as string);
      } else setSynthPending(true);
    } catch {
      setErr("재가공본을 불러오지 못했어요.");
    } finally {
      setLoading(false);
    }
  }

  function openModal() {
    setOpen(true);
    if (!synth) load();
  }

  // Esc 닫기 + 배경 스크롤 잠금
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <>
      <button className="read-btn" type="button" onClick={openModal}>
        {loggedIn ? "읽기 →" : "자세히 →"}
      </button>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-label={title}
            onClick={(e) => e.stopPropagation()}
          >
            <button className="modal-close" type="button" onClick={() => setOpen(false)} aria-label="닫기">
              ✕
            </button>
            <h3 className="modal-title">
              {title}
              {showTitleToggle && (
                <button
                  type="button"
                  className="title-tr-toggle"
                  onClick={() => setKoOpen((o) => !o)}
                >
                  {koOpen ? "접기" : "번역 보기"}
                </button>
              )}
            </h3>
            {showTitleToggle && koOpen && <p className="modal-title-ko">{ko}</p>}
            {levelUp && <span className="level-up">레벨 업! → {levelUp}</span>}

            <div className="modal-body">
              {loading && <p className="synth-err">여는 중…</p>}
              {err && <p className="synth-err">{err}</p>}
              {synthPending && (
                <p className="synth-pending">
                  재가공본을 준비 중이에요.
                  {url && (
                    <>
                      {" "}
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        원문에서 직접 확인해 보세요 ↗
                      </a>
                    </>
                  )}
                </p>
              )}
              {synth && <SynthBody synth={synth} />}
            </div>

            {url && !synthPending && (
              <a className="modal-origin" href={url} target="_blank" rel="noopener noreferrer">
                원문 보기 ↗
              </a>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function SynthBody({ synth }: { synth: Synth }) {
  const takeaways = Array.isArray(synth.key_takeaways) ? synth.key_takeaways : [];
  // title_ko(제목 번역)는 본문 섹션이 아니라 제목용이므로 바디 나열에서 제외(HIVE-66).
  const skip = new Set(["one_liner", "key_takeaways", "content_type", "title_ko"]);
  const body = Object.entries(synth).filter(([k, v]) => {
    if (skip.has(k) || v == null) return false;
    if (typeof v === "string") return v.trim().length > 0;
    if (Array.isArray(v)) return v.length > 0;
    return false;
  });

  return (
    <>
      {synth.one_liner && <p className="modal-lead">{synth.one_liner}</p>}
      {takeaways.length > 0 && (
        <div className="synth-block">
          <h4>핵심 정리</h4>
          <ul>
            {takeaways.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      {body.map(([k, v]) => (
        <div className="synth-block" key={k}>
          <h4>{SYNTH_BODY_LABELS[k] ?? k}</h4>
          {Array.isArray(v) ? (
            <ul>
              {v.map((x, i) => (
                <li key={i}>{String(x)}</li>
              ))}
            </ul>
          ) : (
            <p>{String(v)}</p>
          )}
        </div>
      ))}
    </>
  );
}
