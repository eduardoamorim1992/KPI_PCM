import { useQuery } from "@tanstack/react-query";
import { getDashboardResumo, getRanking } from "../api";

export function useResumo(params = {}) {
  return useQuery({
    queryKey: ["dashboard-resumo", params],
    queryFn: () => getDashboardResumo(params),
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useRanking(topN = 10, grupo) {
  return useQuery({ queryKey: ["ranking", topN, grupo], queryFn: () => getRanking(topN, grupo) });
}
