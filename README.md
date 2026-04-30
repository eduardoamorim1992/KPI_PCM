# Sistema PCM - KPI e Confiabilidade

Stack completo para analise de manutencao (PCM) de frota agroindustrial com:

- Backend `FastAPI` para KPIs, confiabilidade (Weibull) e Monte Carlo.
- Frontend `React + Recharts` para dashboard executivo e paginas analiticas.
- Dados via planilha `parametro.xlsx`.

## Estrutura

- `backend/` API e motores analiticos
- `frontend/` Interface web
- `docker-compose.yml` Execucao integrada

## Rodar localmente

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Docker

```bash
docker compose up --build
```

## Endpoints principais

- `GET /api/dashboard/resumo`
- `GET /api/dashboard/ranking-criticos`
- `GET /api/equipamentos/{cod}/kpis`
- `GET /api/equipamentos/{cod}/confiabilidade`
- `POST /api/simulacao/monte-carlo/{cod}`
- `GET /api/simulacao/frota`
