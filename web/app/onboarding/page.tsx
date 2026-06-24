import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { OnboardingForm } from "@/components/OnboardingForm";

export const metadata = { title: "시작하기 · Dev-Hive" };

export default async function OnboardingPage() {
  // 이미 세션이 있으면 홈으로.
  if (await getSession()) redirect("/");

  return (
    <main className="feed onboard-page">
      <header className="sec-head">
        <h2>Dev-Hive 시작하기</h2>
        <p>3분이면 충분해요. 지금 수준만 알려주면 학습 경로와 추천이 맞춰집니다.</p>
      </header>
      <OnboardingForm />
    </main>
  );
}
