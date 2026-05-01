import { useMemo, useState } from "react";
import Dashboard from "./pages/Dashboard";
import Frota from "./pages/Frota";
import Analitico from "./pages/Analitico";

const pages = {
  dashboard: { label: "Dashboard", Component: Dashboard },
  frota: { label: "Frota", Component: Frota },
  analitico: { label: "Analítico", Component: Analitico },
};

function App() {
  const [active, setActive] = useState("dashboard");
  const Current = useMemo(() => pages[active].Component, [active]);

  return (
    <div className="grid min-h-screen bg-pcm-base text-slate-100 md:grid-cols-[240px_1fr]">
      <aside className="border-b border-white/[0.08] bg-[#0d1324] p-4 md:border-b-0 md:border-r">
        <div className="mb-6">
          <p className="text-[10px] uppercase tracking-[0.4em] text-slate-500">PCM</p>
          <h1 className="text-lg font-semibold text-white">Gestão de manutenção</h1>
        </div>
        <nav className="flex flex-col gap-1">
          {Object.entries(pages).map(([key, { label }]) => (
            <button
              key={key}
              type="button"
              onClick={() => setActive(key)}
              className={`rounded-lg border px-3 py-2 text-left text-sm transition ${
                active === key
                  ? "border-pcm-cyan/40 bg-pcm-cyan/10 text-pcm-cyan"
                  : "border-transparent text-slate-300 hover:border-white/10 hover:bg-white/5"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="px-4 py-6 lg:px-8">
        <Current />
      </main>
    </div>
  );
}

export default App;
