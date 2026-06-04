import { lazy, Suspense } from "react";
import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Layout } from "@/components/layout";
import { I18nProvider } from "@/lib/i18n";

const Dashboard = lazy(() => import("@/pages/dashboard"));
const Markets = lazy(() => import("@/pages/markets"));
const Positions = lazy(() => import("@/pages/positions"));
const Signals = lazy(() => import("@/pages/signals"));
const Trades = lazy(() => import("@/pages/trades"));
const Risk = lazy(() => import("@/pages/risk"));
const Paper = lazy(() => import("@/pages/paper"));
const Strategies = lazy(() => import("@/pages/strategies"));
const Settings = lazy(() => import("@/pages/settings"));
const NotFound = lazy(() => import("@/pages/not-found"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 5000,
      retry: 1,
    },
  },
});

function Router() {
  return (
    <Layout>
      <Suspense fallback={<div className="min-h-screen bg-slate-950" />}>
        <Switch>
          <Route path="/" component={Dashboard} />
          <Route path="/markets" component={Markets} />
          <Route path="/positions" component={Positions} />
          <Route path="/signals" component={Signals} />
          <Route path="/trades" component={Trades} />
          <Route path="/risk" component={Risk} />
          <Route path="/paper" component={Paper} />
          <Route path="/strategies" component={Strategies} />
          <Route path="/settings" component={Settings} />
          <Route component={NotFound} />
        </Switch>
      </Suspense>
    </Layout>
  );
}

function App() {
  return (
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <Router />
          </WouterRouter>
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </I18nProvider>
  );
}

export default App;
