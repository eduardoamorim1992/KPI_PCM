import { CHART_COLORS } from "../theme/chartTheme";

export default function GaugeDM({ valor = 0, meta = 85, label = "DM" }) {
  const v = Math.max(0, Math.min(100, Number(valor)));
  const angle = (v / 100) * 180;
  const cor = v >= meta ? CHART_COLORS.success : v >= meta - 10 ? CHART_COLORS.secondary : CHART_COLORS.danger;

  return (
    <div className="flex flex-col items-center justify-center py-2">
      <svg width="200" height="110" viewBox="0 0 200 110" className="font-mono">
        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="14" strokeLinecap="round" />
        <path
          d="M 20 100 A 80 80 0 0 1 180 100"
          fill="none"
          stroke={cor}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={`${(angle / 180) * 502} 502`}
        />
        <text x="100" y="72" textAnchor="middle" fill="#F1F5F9" fontSize="26" fontWeight="700">
          {v.toFixed(1)}%
        </text>
        <text x="100" y="94" textAnchor="middle" fill="#64748B" fontSize="11">
          {label} — meta {meta}%
        </text>
      </svg>
    </div>
  );
}
