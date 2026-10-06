"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Gauge, History, Settings } from "lucide-react";

const NAV = [
  { href: "/", label: "Dashboard", icon: Gauge },
  { href: "/history", label: "Test History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sticky top-0 hidden h-screen w-60 flex-col border-r border-slate-200 bg-white px-4 py-6 md:flex">
      <div className="mb-8 flex items-center gap-2 px-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Activity size={18} />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">Load Tester</div>
          <div className="text-xs text-slate-500">Authorized testing</div>
        </div>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
        Only test systems you own or are authorized to test.
      </div>
    </aside>
  );
}
