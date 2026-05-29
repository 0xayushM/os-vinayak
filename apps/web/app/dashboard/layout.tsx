import type { Metadata } from "next";
import { Sidebar } from "@/components/dashboard/Sidebar";
import OnboardingGate from "@/components/dashboard/OnboardingGate";

export const metadata: Metadata = {
  title: "Vinayak Brain OS — KBrushes",
  description: "Business intelligence dashboard powered by TranzAct",
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950 text-zinc-100">
      <Sidebar />
      <main className="flex-1 overflow-auto flex flex-col">
        <OnboardingGate>{children}</OnboardingGate>
      </main>
    </div>
  );
}
