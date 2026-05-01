import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import XLSX from "xlsx";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const INPUT_XLSX = path.resolve(PROJECT_ROOT, "parametro.xlsx");
const OUTPUT_JSON = path.resolve(process.cwd(), "public", "data_pcm.json");

const FALHAS_CORRETIVAS_REAIS = new Set([
  "FALHA MECANICA",
  "FALHA ELETRICA",
  "FALHA HIDRAULICA",
  "FALHA LUBRIFICACAO",
  "DESGASTE NATURAL",
  "FALHA EM PNEUS",
  "OBSTACULO PROCESSO",
  "FALHA OPERACIONAL",
  "PANE SECA/FALTA COMB",
  "ACIDENTE",
]);

function normTxt(v) {
  if (v == null) return "";
  return String(v)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toUpperCase();
}

function toIsoDate(v) {
  if (!v) return null;
  if (v instanceof Date) return new Date(v.getTime() - v.getTimezoneOffset() * 60000).toISOString();
  // xlsx can give numbers (Excel serial)
  if (typeof v === "number") {
    const d = XLSX.SSF.parse_date_code(v);
    if (!d) return null;
    const dt = new Date(Date.UTC(d.y, d.m - 1, d.d, d.H || 0, d.M || 0, d.S || 0));
    return dt.toISOString();
  }
  const dt = new Date(v);
  return Number.isFinite(dt.getTime()) ? dt.toISOString() : null;
}

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function main() {
  if (!fs.existsSync(INPUT_XLSX)) {
    console.error(`Arquivo não encontrado: ${INPUT_XLSX}`);
    process.exit(1);
  }

  const wb = XLSX.readFile(INPUT_XLSX, { cellDates: true });
  const ws = wb.Sheets["VW_ORDEM_SERVICO_SAF_PCM"] || wb.Sheets[wb.SheetNames[0]];
  if (!ws) {
    console.error("Planilha não encontrada.");
    process.exit(1);
  }

  const rows = XLSX.utils.sheet_to_json(ws, { defval: null });

  const out = [];
  for (const r of rows) {
    // Mapear colunas do Excel (originais) -> campos normalizados
    const dtEntrada = toIsoDate(r.DT_ENTRADA);
    const cod = num(r.CD_EQUIPTO);
    if (!dtEntrada || cod == null) continue;

    const horasParado = num(r.QT_HR_PERMAN) ?? 0;
    if (horasParado < 0 || horasParado > 8760) continue;

    const tipoFalha = normTxt(r.DE_MOTENTR);
    const origemOs = normTxt(r.FG_ORIGEM);

    const tipoManutencao =
      origemOs === "C" ? "CORRETIVA" : origemOs === "I" ? "PROGRAMADA" : origemOs === "T" ? "TERCEIRIZADA" : "OUTROS";

    const dtSaida = toIsoDate(r.DT_SAIDA);

    out.push({
      // chaves
      num_os: num(r.NO_BOLETIM),
      cod_equipamento: cod,
      grupo_equipamento: normTxt(r.DE_GRUPO_OP),
      modelo: normTxt(r.DE_MODELO),
      marca: normTxt(r.DE_MARCA),
      unidade: normTxt(r.INSTANCIA),
      unidade_medida: normTxt(r.CD_UNIMED),
      status_os: normTxt(r.FG_STATUS_OS),
      tipo_falha: tipoFalha,
      origem_os: origemOs,
      tipo_manutencao: tipoManutencao,

      // datas
      dt_entrada: dtEntrada,
      dt_saida: dtSaida,

      // medidas
      horas_parado: horasParado,
      km_hr_percorrido: num(r.QT_KM_HR),
      acumulado_km_hr: num(r.ACM_KM_HR),
      horimetro_referencia: num(r.NO_HOR_ODOM),
      ano_fabricacao: num(r.NO_ANOFABR),

      // derivados
      is_falha_real: FALHAS_CORRETIVAS_REAIS.has(tipoFalha),
    });
  }

  fs.mkdirSync(path.dirname(OUTPUT_JSON), { recursive: true });
  fs.writeFileSync(
    OUTPUT_JSON,
    JSON.stringify(
      {
        meta: {
          generated_at: new Date().toISOString(),
          source_file: "parametro.xlsx",
          n_rows: out.length,
        },
        rows: out,
      },
      null,
      0
    ),
    "utf-8"
  );

  console.log(`OK: gerado ${OUTPUT_JSON} (${out.length} linhas)`);
}

main();

