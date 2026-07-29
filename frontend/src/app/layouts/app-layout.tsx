import { Outlet, useLocation } from "react-router-dom";

import { AppSidebar } from "@/components/app-sidebar";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

const titles: Record<string, string> = { "/scanner": "Scanner", "/market": "Marché" };

export function AppLayout() {
  const location = useLocation();
  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full">
        <AppSidebar />
        <SidebarInset className="min-w-0 flex-1">
          <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
            <SidebarTrigger aria-label="Ouvrir la navigation" />
            <Separator orientation="vertical" className="h-4" />
            <span className="text-sm font-medium">{titles[location.pathname] ?? "Crypto Dashboard"}</span>
          </header>
          <main className="flex flex-1 flex-col p-4 lg:p-6">
            <div className="mx-auto w-full max-w-[1600px]">
              <Outlet />
            </div>
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
