import { redirect } from "next/navigation";

import { ProfileEditForm } from "@/components/ProfileEditForm";
import { getEditableProfile } from "@/lib/api";
import { getSession } from "@/lib/session";

export const metadata = { title: "정보 수정 · Dev-Hive" };
export const dynamic = "force-dynamic";

export default async function ProfileEditPage() {
  const session = await getSession();
  if (!session) redirect("/onboarding");

  const profile = await getEditableProfile(session.token);

  return (
    <main className="feed onboard-page">
      <header className="sec-head">
        <h2>정보 수정</h2>
        <p>시작할 때 입력한 수준 정보를 다시 조정해 추천과 학습 경로를 새로 맞춥니다.</p>
      </header>
      <ProfileEditForm profile={profile} />
    </main>
  );
}
