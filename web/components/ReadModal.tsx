"use client";

import { useEffect, useState } from "react";
import { SYNTH_BODY_LABELS, contentTypeLabel, externalUrl } from "@/lib/viewmodel";

type Synth = Record<string, unknown> & {
  one_liner?: string;
  key_takeaways?: string[];
  content_type?: string;
};

// '읽기' → 현재 페이지 위에 모달(오버레이 카드)로 재가공본을 띄운다. 이동 아님.
// 열 때 BFF /api/read 1회: 재가공본(캐시 우선) + 로그인 시 읽음 처리.
// 레이아웃(재디자인): 헤더(타입 배지·제목·한 줄 요약) 고정 + 본문(아이콘 스파인) 스크롤 + 푸터('원문 보기' 우하단).
export function ReadModal({
  contentId,
  title,
  url,
  loggedIn,
  titleKo,
  renderTrigger,
}: {
  contentId: number;
  title: string;
  url?: string | null;
  loggedIn: boolean;
  titleKo?: string | null;
  // 트리거를 외부에서 주입(예: 카드 제목 클릭). 없으면 기존 '읽기 →' 버튼을 그대로 렌더(그래프 등).
  renderTrigger?: (open: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [synth, setSynth] = useState<Synth | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [synthPending, setSynthPending] = useState(false);
  const [levelUp, setLevelUp] = useState<string | null>(null);
  const [koOpen, setKoOpen] = useState(false);
  // 호출처가 url을 안 넘기는 경우(예: 지식그래프 노드)를 위해 /api/read 응답의 url을 폴백으로 쓴다.
  const [fetchedUrl, setFetchedUrl] = useState<string | null>(null);
  // 사용자 업로드 원문(외부 링크 없음) — 있으면 '원문 보기'로 펼쳐 보여준다.
  const [originBody, setOriginBody] = useState<string | null>(null);
  const [originOpen, setOriginOpen] = useState(false);
  // user:// 같은 합성 url은 외부 링크로 쓰지 않는다(http/https만 통과).
  const originUrl = externalUrl(url ?? fetchedUrl);

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
      if (data?.url) setFetchedUrl(data.url as string);
      if (data?.body) setOriginBody(data.body as string); // 사용자 업로드 원문
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

  const ct = synth?.content_type;

  return (
    <>
      {renderTrigger ? (
        renderTrigger(openModal)
      ) : (
        <button className="read-btn" type="button" onClick={openModal}>
          {loggedIn ? "읽기 →" : "자세히 →"}
        </button>
      )}

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-label={title}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <div className="modal-head-row">
                {ct && (
                  <span className="synth-badge">
                    <Icon name="spark" size={13} />
                    {contentTypeLabel(ct)}
                  </span>
                )}
                <button className="modal-close" type="button" onClick={() => setOpen(false)} aria-label="닫기">
                  <Icon name="close" size={18} />
                </button>
              </div>
              <h3 className="modal-title">
                {title}
                {showTitleToggle && (
                  <button type="button" className="title-tr-toggle" onClick={() => setKoOpen((o) => !o)}>
                    {koOpen ? "접기" : "번역 보기"}
                  </button>
                )}
              </h3>
              {showTitleToggle && koOpen && <p className="modal-title-ko">{ko}</p>}
              {levelUp && <span className="level-up">레벨 업! → {levelUp}</span>}
              {synth?.one_liner && <p className="modal-lead">{synth.one_liner}</p>}
            </div>

            <div className="modal-body mc-scroll">
              {loading && <p className="synth-err">여는 중…</p>}
              {err && <p className="synth-err">{err}</p>}
              {synthPending && (
                <p className="synth-pending">
                  재가공본을 준비 중이에요.
                  {originUrl && (
                    <>
                      {" "}
                      <a href={originUrl} target="_blank" rel="noopener noreferrer">
                        원문에서 직접 확인해 보세요 ↗
                      </a>
                    </>
                  )}
                </p>
              )}
              {synth && <SynthBody synth={synth} />}

              {/* 사용자 업로드: 외부 원문이 없으므로 업로드한 원문을 모달 안에서 펼쳐 보여준다. */}
              {originBody && (
                <div className="origin-block">
                  <button
                    type="button"
                    className="modal-origin as-toggle"
                    aria-expanded={originOpen}
                    onClick={() => setOriginOpen((o) => !o)}
                  >
                    {originOpen ? "업로드 원문 접기" : "업로드 원문 보기"} <Icon name="doc" size={14} />
                  </button>
                  {originOpen && <p className="origin-body">{originBody}</p>}
                </div>
              )}
            </div>

            {originUrl && !synthPending && (
              <div className="modal-foot">
                <a className="modal-origin" href={originUrl} target="_blank" rel="noopener noreferrer">
                  원문 보기 <Icon name="ext" size={14} />
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// 섹션 키 → 시각 처리(kind)·아이콘. 값 타입과 키로 결정한다.
const WARN_KEYS = new Set(["pitfalls", "gotchas", "counterpoints"]);
const CLOCK_KEYS = new Set(["when_to_use", "when_matters"]);

type Kind = "key" | "warn" | "chips" | "bullets" | "para";

function sectionKind(key: string, value: unknown): { kind: Kind; icon: IconName } {
  if (key === "key_takeaways") return { kind: "key", icon: "spark" };
  if (WARN_KEYS.has(key)) return { kind: "warn", icon: "warn" };
  if (key === "requirements") return { kind: "chips", icon: "doc" };
  if (Array.isArray(value)) return { kind: "bullets", icon: "list" };
  if (CLOCK_KEYS.has(key)) return { kind: "para", icon: "clock" };
  return { kind: "para", icon: "info" };
}

function SynthBody({ synth }: { synth: Synth }) {
  const takeaways = Array.isArray(synth.key_takeaways) ? synth.key_takeaways : [];
  // 본문 섹션이 아닌 키(요약·태그성)는 스파인에서 제외.
  const skip = new Set([
    "one_liner", "key_takeaways", "content_type", "title_ko",
    "language", "quality_score", "off_topic", "relevance", "difficulty",
  ]);
  const body = Object.entries(synth).filter(([k, v]) => {
    if (skip.has(k) || v == null) return false;
    if (typeof v === "string") return v.trim().length > 0;
    if (Array.isArray(v)) return v.length > 0;
    return false;
  });

  const sections: [string, unknown][] = [];
  if (takeaways.length > 0) sections.push(["key_takeaways", takeaways]);
  sections.push(...body);

  return (
    <div className="synth-spine">
      {sections.map(([k, v]) => {
        const { kind, icon } = sectionKind(k, v);
        const label = k === "key_takeaways" ? "핵심 정리" : SYNTH_BODY_LABELS[k] ?? k;
        const nodeClass = kind === "key" ? "is-key" : kind === "warn" ? "is-warn" : "is-def";
        return (
          <div className="synth-row" key={k}>
            <span className={`synth-node ${nodeClass}`} aria-hidden>
              <Icon name={icon} size={kind === "key" ? 15 : 16} />
            </span>
            <div className="synth-col">
              <div className={`synth-h${kind === "warn" ? " is-warn" : ""}`}>{label}</div>
              <SectionContent kind={kind} value={v} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SectionContent({ kind, value }: { kind: Kind; value: unknown }) {
  const items = Array.isArray(value) ? value.map((x) => String(x)) : [];

  if (kind === "key") {
    return (
      <div className="synth-hl">
        {items.map((t, i) => (
          <div className="synth-hl-item" key={i}>
            <span className="synth-check" aria-hidden>
              <Icon name="check" size={15} />
            </span>
            <span>{renderInline(t)}</span>
          </div>
        ))}
      </div>
    );
  }
  if (kind === "warn") {
    return (
      <div className="synth-warn">
        {items.map((t, i) => (
          <div className="synth-warn-item" key={i}>
            <span className="synth-wdot" aria-hidden />
            <span>{renderInline(t)}</span>
          </div>
        ))}
      </div>
    );
  }
  if (kind === "chips") {
    return (
      <div className="synth-chips">
        {items.map((t, i) => (
          <span className="synth-chip" key={i}>
            {t}
          </span>
        ))}
      </div>
    );
  }
  if (kind === "bullets") {
    return (
      <div className="synth-bullets">
        {items.map((t, i) => (
          <div className="synth-bullet" key={i}>
            <span className="synth-dot" aria-hidden />
            <span>{renderInline(t)}</span>
          </div>
        ))}
      </div>
    );
  }
  return <RichText text={String(value)} />;
}

// 인라인 마크다운: `code` → <code> 스타일.
function renderInline(s: string): React.ReactNode {
  return s.split(/(`[^`]+`)/g).map((p, i) =>
    p.length > 2 && p.startsWith("`") && p.endsWith("`") ? (
      <code className="synth-code" key={i}>
        {p.slice(1, -1)}
      </code>
    ) : (
      p
    )
  );
}

// 문단에 인라인 리스트(" - " / 줄머리 "- ·")가 섞여 오면 불릿으로 분리하고, 백틱은 코드로 렌더.
function RichText({ text }: { text: string }) {
  const norm = text.replace(/\s+[-•]\s+/g, "\n- ").trim();
  const lines = norm.split("\n");
  const lead: string[] = [];
  const items: string[] = [];
  for (const ln of lines) {
    const m = ln.match(/^[-•]\s+(.*)/);
    if (m) items.push(m[1].trim());
    else lead.push(ln);
  }
  if (items.length < 2) return <p className="synth-para">{renderInline(text)}</p>;
  const leadText = lead.join(" ").trim();
  return (
    <>
      {leadText && <p className="synth-para">{renderInline(leadText)}</p>}
      <div className="synth-bullets" style={{ marginTop: leadText ? 10 : 0 }}>
        {items.map((it, i) => (
          <div className="synth-bullet" key={i}>
            <span className="synth-dot" aria-hidden />
            <span>{renderInline(it)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

// ── 인라인 아이콘(스파인 노드·배지·체크) ──
type IconName = "spark" | "info" | "clock" | "list" | "warn" | "doc" | "check" | "close" | "ext";

const PATHS: Record<IconName, { d: string; w?: number }> = {
  spark: { d: "M12 4l1.5 4.1L18 9.6l-4.5 1.5L12 16l-1.5-4.9L6 9.6l4.5-1.5L12 4z" },
  info: { d: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 16v-4M12 8h.01" },
  clock: { d: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7.5V12l3 2" },
  list: { d: "M11 6h9M11 12h9M11 18h9M3.5 6.2l1.2 1.2 2.3-2.4M3.5 12.2l1.2 1.2 2.3-2.4M3.5 18.2l1.2 1.2 2.3-2.4" },
  warn: { d: "M12 4.5l8.5 15h-17l8.5-15zM12 10v4M12 17.5h.01" },
  doc: { d: "M8 5h8a2 2 0 012 2v12a2 2 0 01-2 2H8a2 2 0 01-2-2V7a2 2 0 012-2zM9.5 11h5M9.5 15h5" },
  check: { d: "M4.5 12.5l4.5 4.5 10.5-11", w: 2.4 },
  close: { d: "M6 6l12 12M18 6L6 18", w: 1.8 },
  ext: { d: "M7 17L17 7M8 7h9v9", w: 2 },
};

function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  const { d, w } = PATHS[name];
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={w ?? 1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {d.split("M").filter(Boolean).map((seg, i) => (
        <path key={i} d={"M" + seg} />
      ))}
    </svg>
  );
}
