import * as React from "react";
import { Activity, FlaskConical, Search, TrendingUp } from "lucide-react";

import { NavMain } from "@/components/nav-main";
import { Sidebar, SidebarContent, SidebarHeader, SidebarRail } from "@/components/ui/sidebar";

const navItems = [
  { title: "Scanner", url: "/scanner", icon: Search },
  { title: "Backtests", url: "/backtests", icon: FlaskConical },
  { title: "Expériences", url: "/backtests/experiments", icon: FlaskConical },
  { title: "Marché en temps réel", url: "/market", icon: Activity },
];

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="border-b">
        <div className="flex items-center gap-2">
          <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
            <TrendingUp className="size-4" />
          </div>
          <div className="flex flex-col">
            <span className="truncate text-sm font-semibold">Crypto Dashboard</span>
            <span className="truncate text-xs text-muted-foreground">Trading & Scanner</span>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navItems} />
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}
