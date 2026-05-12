/**
 * Dashboard shell layout — R-36, 4.C.12.
 *
 * RSC layout: renders persistent Sidebar + Topbar wrapping all dashboard pages.
 */

import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-background)]">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-auto p-[var(--spacing-lg)]">
          {children}
        </main>
      </div>
    </div>
  );
}
