import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useFilterStore = create(
  persist(
    (set) => ({
      grupo: "",
      unidade: "",
      frota: "",
      modelo: "",
      codEquipamento: "",
      setGrupo: (grupo) => set({ grupo }),
      setUnidade: (unidade) => set({ unidade }),
      setFrota: (frota) => set({ frota }),
      setModelo: (modelo) => set({ modelo }),
      setCodEquipamento: (codEquipamento) => set({ codEquipamento }),
      reset: () => set({ grupo: "", unidade: "", frota: "", modelo: "", codEquipamento: "" }),
    }),
    { name: "pcm-filtros-v1" },
  ),
);
