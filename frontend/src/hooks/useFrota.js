import { useQuery } from "@tanstack/react-query";
import { getEquipamentos, getGrupos } from "../api";

export function useGrupos() {
  return useQuery({ queryKey: ["grupos"], queryFn: getGrupos });
}

export function useEquipamentos(filters = {}) {
  return useQuery({ queryKey: ["equipamentos", filters], queryFn: () => getEquipamentos(filters) });
}
