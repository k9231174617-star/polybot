import { useState, type ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { useGetBotStatus, getGetBotStatusQueryKey, useControlBot } from "@workspace/api-client-react";
import { Play, Square, Pause, Activity, LineChart, Table2, Radar, ArrowLeftRight, ShieldAlert, Settings, FlaskConical, Menu, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n";

export function Layout({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { data: botStatus } = useGetBotStatus({ query: { queryKey: getGetBotStatusQueryKey() } });
  const controlBot = useControlBot();
  const { lang, setLang, t } = useI18n();

  const navItems = [
    { href: "/", label: t("nav_dashboard"), icon: Activity },
    { href: "/markets", label: t("nav_markets"), icon: Radar },
    { href: "/positions", label: t("nav_positions"), icon: Table2 },
    { href: "/signals", label: t("nav_signals"), icon: LineChart },
    { href: "/trades", label: t("nav_trades"), icon: ArrowLeftRight },
    { href: "/risk", label: t("nav_risk"), icon: ShieldAlert },
    { href: "/paper", label: t("nav_paper"), icon: FlaskConical },
    { href: "/strategies", label: t("nav_strategies"), icon: BarChart3 },
    { href: "/settings", label: t("nav_settings"), icon: Settings },
  ];

  const statusTone = cn("w-2 h-2 rounded-full", {
    "bg-success shadow-[0_0_8px_rgba(34,197,94,0.6)]": botStatus?.state === "running",
    "bg-warning shadow-[0_0_8px_rgba(245,158,11,0.6)]": botStatus?.state === "paused",
    "bg-muted-foreground": botStatus?.state === "stopped",
    "bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.6)]": botStatus?.state === "error",
  });

  const closeMobileNav = () => setMobileNavOpen(false);

  const toggleLang = () => setLang(lang === "en" ? "ru" : "en");

  return (
    <div className="flex min-h-screen w-full bg-background overflow-hidden selection:bg-primary/30">
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="w-[88vw] max-w-sm p-0 bg-card">
          <div className="flex h-full flex-col">
            <SheetHeader className="border-b border-border px-4 py-4 text-left">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <SheetTitle className="flex items-center gap-2 font-mono text-base tracking-tight">
                    <div className="w-3 h-3 bg-primary rounded-sm animate-pulse shrink-0" />
                    POLYBOT.TERM
                  </SheetTitle>
                  <SheetDescription className="text-xs uppercase tracking-[0.24em]">
                    {t("system_status")}
                  </SheetDescription>
                </div>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8 shrink-0 font-mono text-[10px]"
                  onClick={toggleLang}
                  data-testid="lang-toggle"
                  aria-label="Toggle language"
                >
                  {lang.toUpperCase()}
                </Button>
              </div>
            </SheetHeader>

            <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-1 px-3">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = location === item.href;
                return (
                  <Link key={item.href} href={item.href}>
                    <div
                      onClick={closeMobileNav}
                      className={cn(
                        "flex items-center gap-3 px-3 py-3 rounded-md text-sm font-medium transition-colors cursor-pointer",
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:text-foreground hover:bg-secondary"
                      )}
                    >
                      <Icon className="w-4 h-4" />
                      {item.label}
                    </div>
                  </Link>
                );
              })}
            </div>

            <div className="p-4 border-t border-border bg-card/50">
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-medium text-muted-foreground">{t("system_status")}</span>
                <div className="flex items-center gap-2">
                  <div className={statusTone} />
                  <span className="text-xs font-mono uppercase text-foreground">{botStatus?.state || "UNKNOWN"}</span>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Button
                  variant="outline"
                  className={cn("w-full h-9", botStatus?.state === "running" && "border-success text-success bg-success/10")}
                  onClick={() => {
                    controlBot.mutate({ data: { action: "start" } });
                    closeMobileNav();
                  }}
                  disabled={botStatus?.state === "running"}
                >
                  <Play className="w-4 h-4" />
                </Button>
                <Button
                  variant="outline"
                  className={cn("w-full h-9", botStatus?.state === "paused" && "border-warning text-warning bg-warning/10")}
                  onClick={() => {
                    controlBot.mutate({ data: { action: "pause" } });
                    closeMobileNav();
                  }}
                  disabled={botStatus?.state !== "running"}
                >
                  <Pause className="w-4 h-4" />
                </Button>
                <Button
                  variant="outline"
                  className="w-full h-9 hover:border-destructive hover:text-destructive hover:bg-destructive/10"
                  onClick={() => {
                    controlBot.mutate({ data: { action: "stop" } });
                    closeMobileNav();
                  }}
                  disabled={botStatus?.state === "stopped" || !botStatus}
                >
                  <Square className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <div className="hidden md:flex w-64 border-r border-border bg-card flex-col shrink-0">
        <div className="h-16 flex items-center px-4 border-b border-border gap-2">
          <div className="flex items-center gap-2 text-primary font-mono font-bold tracking-tight flex-1 min-w-0">
            <div className="w-3 h-3 bg-primary rounded-sm animate-pulse shrink-0" />
            <span className="truncate">POLYBOT.TERM</span>
          </div>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0 font-mono text-[10px]"
            onClick={toggleLang}
            data-testid="lang-toggle"
            aria-label="Toggle language"
          >
            {lang.toUpperCase()}
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto py-6 flex flex-col gap-1 px-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location === item.href;
            return (
              <Link key={item.href} href={item.href}>
                <div className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary"
                )}>
                  <Icon className="w-4 h-4" />
                  {item.label}
                </div>
              </Link>
            );
          })}
        </div>

        <div className="p-4 border-t border-border bg-card/50">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-medium text-muted-foreground">{t("system_status")}</span>
            <div className="flex items-center gap-2">
              <div className={statusTone} />
              <span className="text-xs font-mono uppercase text-foreground">{botStatus?.state || "UNKNOWN"}</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Button
              variant="outline"
              size="icon"
              className={cn("w-full h-8", botStatus?.state === "running" && "border-success text-success bg-success/10")}
              onClick={() => controlBot.mutate({ data: { action: "start" } })}
              disabled={botStatus?.state === "running"}
            >
              <Play className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className={cn("w-full h-8", botStatus?.state === "paused" && "border-warning text-warning bg-warning/10")}
              onClick={() => controlBot.mutate({ data: { action: "pause" } })}
              disabled={botStatus?.state !== "running"}
            >
              <Pause className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="w-full h-8 hover:border-destructive hover:text-destructive hover:bg-destructive/10"
              onClick={() => controlBot.mutate({ data: { action: "stop" } })}
              disabled={botStatus?.state === "stopped" || !botStatus}
            >
              <Square className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 border-b border-border/70 bg-card/95 backdrop-blur md:hidden">
          <div className="flex items-center gap-3 px-4 py-3">
            <Button
              variant="outline"
              size="icon"
              className="h-9 w-9 shrink-0"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="h-4 w-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-mono text-sm font-bold tracking-tight">POLYBOT.TERM</span>
                <span className="text-[10px] font-mono uppercase text-muted-foreground">mobile</span>
              </div>
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.24em] text-muted-foreground">
                <span>{t("system_status")}</span>
                <span className={statusTone} />
                <span className="font-mono text-foreground">{botStatus?.state || "UNKNOWN"}</span>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto bg-background p-4 pb-8 md:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
