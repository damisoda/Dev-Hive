import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dev-Hive Frontend",
  description: "Dev-Hive frontend environment",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
