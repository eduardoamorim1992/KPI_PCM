import { useQuery } from "@tanstack/react-query";
import { getAnaliticoOverview } from "../api";

export function useAnalitico(params = {}) {
  return useQuery({ queryKey: ["analitico-overview", params], queryFn: () => getAnaliticoOverview(params) });
}
