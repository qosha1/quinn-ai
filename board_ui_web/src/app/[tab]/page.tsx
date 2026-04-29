import { notFound } from "next/navigation";
import { BoardShell, type Tab } from "@/components/BoardShell";

const VALID_TABS = new Set(["dashboard", "team", "messages", "work", "activity"]);

export function generateStaticParams() {
  return [
    { tab: "dashboard" },
    { tab: "team" },
    { tab: "messages" },
    { tab: "work" },
    { tab: "activity" },
  ];
}

export default async function TabPage({ params }: { params: Promise<{ tab: string }> }) {
  const { tab } = await params;
  if (!VALID_TABS.has(tab)) notFound();
  return <BoardShell tab={tab as Tab} />;
}
