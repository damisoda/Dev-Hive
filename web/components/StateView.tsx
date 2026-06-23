// 빈 상태 / 에러 상태 공용 뷰.

export function StateView({
  emoji,
  title,
  children,
}: {
  emoji: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="state">
      <span className="emoji">{emoji}</span>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </div>
  );
}
