# ApexSim: Checklist de Implementações por Membro e Marco (M0 a M5)

Este documento centraliza todos os entregáveis e requisitos de código, arquitetura, arquivos e funcionalidades previstos no roadmap do **ApexSim** para cada um dos cinco integrantes do grupo. Ele foi estruturado em formato de checklist Markdown para facilitar a análise automatizada por modelos de linguagem e ferramentas de inspeção de código local.

---

## 1. Gabriel Pavani Giro — Motor de Simulação (`sim/`)

### M0 — Fundação (Semanas 1–2)
- [x] **Estruturas de Dados Base (`backend/sim/state.py`)**:
  - [x] Classe/dataclass `RaceState` definida com type hints e docstrings.
  - [x] Classe/dataclass `DriverState` definida (posição, tempo de volta, gap, composto, idade do pneu, combustível, status de pit).
  - [x] Classe/dataclass `LapResult` definida.
  - [x] Assinatura do método/função `tick()` declarada.
  - [x] Teste unitário criando um `RaceState` com 20 pilotos passando sem erros.

### M1 — Verticais Isoladas (Semanas 3–5)
- [x] **Loop Principal com Tempos Constantes**:
  - [x] Lógica de avanço de voltas implementada.
  - [x] Ordenação de posições a cada volta.
  - [x] Cálculo de gaps para o líder e para o carro imediatamente à frente.
- [x] **Sistema de Seed Determinístico**:
  - [x] Instância própria `random.Random(seed)` para garantir reprodutibilidade sem afetar o estado global.
  - [x] Execução `python -m sim.run --laps 50 --seed 42` gera resultados idênticos em rodadas repetidas.
  - [x] Testes unitários do cálculo de gaps validados.

### M2 — Esqueleto Ambulante (Semana 6)
- [x] **Emissão em Tempo Real via WebSocket**:
  - [x] Emissão contínua de mensagens `lap_update` no formato do envelope acordado a cada volta concluída.
  - [x] Suporte e tratamento dos comandos `play`, `pause` e `set_speed` recebidos do cliente.

### M3 — Corrida Realista (Semanas 7–10)
- [x] **Integração de Física e Regras de Corrida**:
  - [x] Substituição dos tempos de volta constantes pelas funções de física (degradação de pneu, peso de combustível e ar sujo).
  - [x] Modelo probabilístico de ultrapassagem baseado em diferencial de ritmo, uso de DRS e dificuldade do circuito (`track_map`).
  - [x] Aplicação mecânica da perda de tempo no pit lane (`time_loss_s`) e atualização do composto do pneu ao receber ordem de pit stop.

### M4 — Feature Complete / Calibração (Semanas 11–13)
- [ ] **Relatório e Processo de Calibração (`docs/calibracao.md`)**:
  - [ ] Simulação de 3 corridas reais (100 rodadas por seed) comparando tempo médio de volta, tempo total de prova, paradas de box e distribuição final.
  - [ ] Erro médio do tempo de volta mantido abaixo de 3% nos três circuitos.

### M5 — Entrega (Semanas 14–15)
- [ ] Documentação completa do motor e preparação da demonstração.

---

## 2. Isaac do Nascimento Oliveira — Física & Eventos (`physics/`)

### M0 — Fundação (Semanas 1–2)
- [x] **Documentação Teórica Inicial (`docs/fisica.md`)**:
  - [x] Definição formal das 4 equações principais (degradação de pneu, consumo de combustível, ar sujo e DRS).
  - [x] Especificação de variáveis, faixas esperadas de parâmetros e fontes/referências declaradas.

### M1 — Verticais Isoladas (Semanas 3–5)
- [x] **Implementação das Funções Puras de Física**:
  - [x] Função pura de degradação de pneu por composto, idade e temperatura.
  - [x] Função pura de tempo delta por peso de combustível (~0,3s por 10kg aliviados).
  - [x] Notebook de validação (`notebooks/validacao_pneus.ipynb`) plotando e comparando as curvas geradas com as curvas reais do Octávio.

### M2 — Esqueleto Ambulante (Semana 6)
- [x] Suporte à integração global do pipeline.

### M3 — Corrida Realista (Semanas 7–10)
- [x] **Mapeamento de Efeitos e Eventos Estocásticos**:
  - [x] Modelo de penalidade de ar sujo em função da proximidade (<2s, cresce rapidamente abaixo de 1s).
  - [x] Efeito de DRS integrado ao `track_map` (verificação de gap <1.0s em `drs_detection` para acionamento em `drs_activation`).
  - [x] Gerador estocástico de acidentes distribuído pelas zonas de frenagem (`braking_zone`), modulado por severidade e tipo de escapatória (`runoff`).
  - [x] Máquina de estados para **Safety Car / VSC** (acionamento, compressão do pelotão, duração e retomada).
  - [x] Atualização do documento `docs/fisica.md` com o modelo de eventos.

### M4 — Feature Complete (Semanas 11–13)
- [ ] **Modelo Climático Dinâmico**:
  - [ ] Cadeia de Markov para transições climáticas entre `seco`, `úmido` e `molhado`.
  - [ ] Ajuste no tempo de volta, grip dos compostos e penalidades por escolha errada de pneu no molhado.

### M5 — Entrega (Semanas 14–15)
- [ ] Defesa final dos coeficientes e seção de física do relatório.

---

## 3. Daniel Franco — Modelagem de Pista, Estratégia & IA (`strategy/` e `docs/`)

### M0 — Fundação (Semanas 1–2)
- [x] **Governança do Repositório**:
  - [x] Branch protection configurada para a branch `main`.
  - [x] Arquivo `CODEOWNERS` e template de Pull Request criados.
  - [x] Convenções de commit documentadas.
- [x] **Schema do Mapa de Pistas (`docs/track_map_schema.md`)**:
  - [x] Especificação técnica do contrato D4 formalizada (tipos de zonas, suporte 1D x 2D e regras de validação).

### M1 — Verticais Isoladas (Semanas 3–5)
- [x] **Ferramenta Interna de Anotação (Editor de Pistas)**:
  - [x] Interface visual que carrega a polyline D3 (Octávio), desenha o traçado e exibe a distância acumulada (`distance_m`).
  - [x] Seleção de intervalos/pontos e definição de zonas semânticas.
  - [x] Exportação do JSON no formato D4.
- [x] **Arquivos de Circuito Anotados**:
  - [x] `track_maps/interlagos.json` commitado.
  - [x] `track_maps/monza.json` commitado.
  - [x] `track_maps/monaco.json` commitado.
- [x] **Script de Validação Lógica**:
  - [x] Script para validar se nenhuma zona excede o `length_m` e se as regras de integridade são respeitadas.

### M2 — Esqueleto Ambulante (Semana 6)
- [x] Validação de carga dos arquivos `track_map` no backend, suporte de integração e governança de PRs.

### M3 — Corrida Realista (Semanas 7–10)
- [x] **Heurística de Pit Stop (Degrau 1 — `backend/strategy/heuristic.py`)**:
  - [x] Algoritmo base comparando prejuízo acumulado de degradação contra o custo total da parada (`time_loss_s`).
  - [x] Reação dinâmica a Safety Car / VSC (antecipação da parada).
  - [x] Reação a Bandeira Vermelha (troca de pneu).
  - [x] Reação a ameaça de Undercut defensivo.
  - [x] Configuração de parâmetro de agressividade por equipe (`aggression` entre 0.0 e 1.0).
  - [x] Testes unitários (`tests/test_strategy.py`) garantindo paradas realistas para todos os pilotos.

### M4 — Feature Complete (Semanas 11–13)
- [ ] **Otimização por Monte Carlo (Degrau 2 — `backend/strategy/monte_carlo.py`)**:
  - [ ] Simulação de $K$ cenários futuros sob incerteza para seleção do momento e composto ideais.
  - [ ] Teste de sanidade (convergência com a heurística em cenários simples).
  - [ ] Execução da simulação completa mantida abaixo de 30 segundos.
  - [ ] Documentação técnica em `docs/estrategia.md`.

### M5 — Entrega (Semanas 14–15)
- [ ] Consolidação do relatório final, revisão geral do repositório e condução da demo do editor.

---

## 4. Anderson Murillo T. L. Leite — Frontend & UX (`frontend/`)

### M0 — Fundação (Semanas 1–2)
- [x] **Scaffold Frontend e Mock Server**:
  - [x] Projeto Next.js + TypeScript + Tailwind CSS configurado com geração automática de tipos OpenAPI.
  - [x] Servidor de mock WebSocket em Node.js emitindo mensagens `lap_update` fictícias a cada 2 segundos.

### M1 — Verticais Isoladas (Semanas 3–5)
- [x] **Telas de Configuração e Timing Tower**:
  - [x] Telas de formulário para seleção de circuito, grid, clima e estratégia inicial.
  - [x] Componente `Timing Tower` funcional (posições, gaps, composto, idade do pneu) integrado com Zustand.
  - [x] Reordenação animada/correta das posições nas ultrapassagens contra o mock.

### M2 — Esqueleto Ambulante (Semana 6)
- [x] **Conexão Real com o Backend**:
  - [x] Substituição da URL do mock pela conexão WebSocket do motor do Gabriel.
  - [x] Envio dos comandos de controle (`play`, `pause`, `set_speed`) para o backend.

### M3 — Corrida Realista (Semanas 7–10)
- [x] **Painel da Direção de Prova e Polimento**:
  - [x] Exibição de alertas de bandeiras, Safety Car e penalidades em tempo real.
  - [x] Animações fluidas de transição de posições na Timing Tower (Framer Motion ou CSS Transitions).

### M4 — Feature Complete (Semanas 11–13)
- [ ] **Minimapa 2D Interativo**:
  - [ ] Renderização 2D da polyline D3 em Canvas ou SVG.
  - [ ] Interpolação suave dos 20 carros ao longo dos pontos `distance_m` entre as mensagens de WebSocket.

### M5 — Entrega (Semanas 14–15)
- [ ] Polimento visual e condução da demonstração ao vivo da interface.

---

## 5. Octávio A. B. do Nascimento — Dados & Plataforma (`backend/db/`, `infra/`)

### M0 — Fundação (Semanas 1–2)
- [x] **Plataforma e Infraestrutura (Semana 1)**:
  - [x] `docker-compose.yml` configurado com serviços `api`, `web`, `db` e volume para cache do FastF1.
  - [x] Scaffold FastAPI com endpoints base e `/health` (resposta 200).
  - [x] GitHub Actions configurado para lint e testes em PRs.
  - [x] `Makefile` com comandos `make up`, `make seed`, `make test`, `make lint`.
- [x] **Geometria Simplificada (Semana 2 — Contrato D3)**:
  - [x] Scripts de extração do FastF1 aplicando algoritmo Ramer–Douglas–Peucker para ~300 pontos com `distance_m`.
  - [x] Arquivos de polyline gerados: `circuits/interlagos.json`, `circuits/monza.json` e `circuits/monaco.json`.

### M1 — Verticais Isoladas (Semanas 3–5)
- [x] **Banco de Dados e Ingestão Kaggle**:
  - [x] Modelagem relacional e migrations com Alembic (tabelas de referência e transacionais).
  - [x] Script de seed idempotente (`make seed`).
  - [x] Mapeamento e reconciliação dos 3 datasets do Kaggle (Contrato D5 - curvas reais de degradação de pneu).

### M2 — Esqueleto Ambulante (Semana 6)
- [x] Suporte de infraestrutura e banco para o loop da corrida burra.

### M3 — Corrida Realista (Semanas 7–10)
- [ ] **Persistência e Analytics I**:
  - [x] Gravação em lote por volta de `lap_records` e `race_events` no PostgreSQL.
  - [x] Endpoint `GET /api/races/{id}/results`.
  - [ ] Gráfico de evolução de posições volta a volta.

### M4 — Feature Complete (Semanas 11–13)
- [ ] **Analytics II (Stint Chart)**:
  - [ ] Gráfico de barras horizontais por stint de pneu e visualização comparativa entre corridas.

### M5 — Entrega (Semanas 14–15)
- [ ] Consolidação do relatório, diagramas de arquitetura e gravação do vídeo de backup da demo.
