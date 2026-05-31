import type { Metadata } from "next";
import "./globals.css";
import Navigation from "@/components/Navigation";

// Inter is loaded via Tailwind/CSS to avoid Google Fonts SSL issues in restricted networks.

export const metadata: Metadata = {
  title: "Ganesh AgentOps",
  description: "AI Agent Orchestration Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-gray-950 text-white font-sans">
        <div className="flex min-h-screen">
          <Navigation />
          <main className="flex-1 ml-56 min-h-screen overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
