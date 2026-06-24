"use client";

import { useState } from "react";
import { SYNTH_BODY_LABELS } from "@/lib/viewmodel";

type Synth = Record<string, unknown> & {
  one_liner?: string;
  key_takeaways?: string[];
};

// '읽기' — 누르면 재가공본(synthesis: 핵심정리 + 타입별 바디)을 펼치고, 로그인 시 읽음 처리.
// 재가공본은 백엔드 캐시 우선(처음 한 번만 생성). 한 번 받으면 다시 누를 때 재요청 없음.
export function ReadMore({ contentId, loggedIn }: { contentId: number; loggedIn: boolean }) {
  const [open, setOpen] = useState(false);
  const [synth, setSynth] = useState<Synth | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [levelUp, setLevelUp] = useState<string | null>(null);

  async function onClick() {
    if (open) {
      setOpen(false);
      return;
    }
    if (synth || err) {
      setOpen(true);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content_id: contentId }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErr(data.error ?? "재가공본을 불러오지 못했어요.");
      } else if (data.synthesis) {
        setSynth(data.synthesis as Synth);
        if (data.leveled_up && data.new_level) setLevelUp(data.new_level as string);
      } else {
        setErr("아직 재가공본이 준비되지 않았어요.");
      }
      setOpen(true);
    } catch {
      setErr("재가공본을 불러오지 못했어요.");
      setOpen(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="read-wrap">
      <button className="read-btn" onClick={onClick} disabled={loading} aria-expanded={open}>
        {loading ? "여는 중…" : open ? "접기 ▴" : loggedIn ? "읽기 ▾" : "자세히 ▾"}
      </button>
      {levelUp && <span className="level-up">레벨 업! → {levelUp}</span>}
      {open && (
        <div className="synth">
          {err ? <p className="synth-err">{err}</p> : synth ? <SynthBody synth={synth} /> : null}
        </div>
      )}
    </div>
  );
}

function SynthBody({ synth }: { synth: Synth }) {
  const takeaways = Array.isArray(synth.key_takeaways) ? synth.key_takeaways : [];
  const skip = new Set(["one_liner", "key_takeaways", "content_type"]);
  const body = Object.entries(synth).filter(([k, v]) => {
    if (skip.has(k) || v == null) return false;
    if (typeof v === "string") return v.trim().length > 0;
    if (Array.isArray(v)) return v.length > 0;
    return false;
  });

  return (
    <>
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
