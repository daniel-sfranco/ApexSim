# ApexSim — Fundamentação Física e Estocástica (`docs/fisica.md`)

> Documento técnico de base para o motor de física e eventos estocásticos do simulador de corridas orientado a eventos ApexSim. Cobre 6 subsistemas: pneus, combustível, ar sujo, DRS, acidentes/falhas e clima. Cada seção traz equações, definição de variáveis, faixas de calibração pós-2022 (era de efeito solo) e referências primárias.

---

## 1. Degradação de Pneus (Tire Wear & Thermal Degradation)

### 1.1 Modelo combinado: desgaste progressivo + cliff térmico/mecânico

A literatura de simulação de estratégia (Heilmeier et al.; Sulsters; F1Metrics; ETH/TUM) converge para decompor o tempo de volta em componentes aditivos, com o termo de pneu modelado como polinomial (linear ou quadrático) por composto, mais um termo de degradação abrupta ("cliff") quando a idade do pneu excede um limiar crítico.

**Forma linear (Heilmeier et al. 2020):**

\[
t_{tire}(a, c) = k_0(c) + k_1(c) \cdot a
\]

**Forma quadrática (Sulsters et al. 2018 / TUM 2021, adotada no ApexSim para capturar curvatura pré-cliff):**

\[
t_{tire,quad}(a, c) = k_{1,quad}(c) \cdot a^2 + k_{2,quad}(c) \cdot a + k_3(c)
\]

**Termo de cliff (degradação abrupta), formulação por função logística/step suavizado recomendada para o motor de eventos:**

\[
t_{cliff}(a,c) = \frac{\Delta_{cliff}(c)}{1 + \exp\left(-\beta\,(a - a_{cliff}(c))\right)}
\]

**Tempo de volta total do pneu:**

\[
t_{lap,tire}(a,c) = t_{tire,quad}(a,c) + t_{cliff}(a,c)
\]

### 1.2 Definição de variáveis

| Símbolo | Definição | Unidade |
|---|---|---|
| \(a\) | Idade do pneu (voltas desde o último pit stop / troca) | voltas |
| \(c\) | Composto (Soft, Medium, Hard, Inter, Wet) | categórico |
| \(k_0, k_1\) | Coeficiente base e coeficiente de degradação linear | s, s/volta |
| \(k_{1,quad}, k_{2,quad}, k_3\) | Coeficientes quadráticos de ajuste por composto | s/volta², s/volta, s |
| \(\Delta_{cliff}(c)\) | Magnitude do salto de degradação no cliff | s |
| \(a_{cliff}(c)\) | Idade (voltas) em que ocorre o cliff | voltas |
| \(\beta\) | Inclinação da transição (quão abrupto é o cliff) | 1/volta |

### 1.3 Faixas de calibração (pós-2022, pneus Pirelli 18")

- Degradação linear média por composto (dados FastF1 2022–2026, regressão por volta): Soft ≈ 0,06–0,09 s/volta; Medium ≈ 0,05–0,065 s/volta; Hard ≈ 0,04–0,055 s/volta. O spread entre compostos variou fortemente por temporada: 0,053 s/volta em 2022, apenas 0,011 s/volta em 2023, 0,043 em 2024, 0,041 em 2025 e 0,008 em 2026 (ano em que a hierarquia se inverteu: o Hard passou a degradar mais rápido, a 0,071 s/volta, contra 0,065 do Medium e 0,063 do Soft)[1].
- Cliff térmico: em pneus C3–C5 da era de efeito solo, o salto de degradação pode variar de 0,3 a 1,5+ s/volta quando o pneu ultrapassa a janela térmica ótima, tipicamente entre a volta 18–30 dependendo do composto e da abrasividade da pista.
- Correção de combustível usada como premissa para isolar o termo de pneu: 0,03–0,08 s/kg (ver Seção 2); os resultados de degradação são robustos a essa faixa[1].

#### Calibração Empírica ApexSim — Entrega D5 (Dataset Kaggle / FastF1 2023–2024)
A calibração direta sobre 39.966 voltas limpas de 44 GPs (`data/curvas_degradacao/curvas_degradacao.json`, com dados até `idade_max_suportada` de 19 voltas no Soft, 29 no Medium e 41 no Hard) resultou nos seguintes parâmetros adotados em `physics.py`:
- **Soft**: \(k_{1,quad} = 0,002412\), \(k_{2,lin} = 0,008639\).
- **Medium**: \(k_{1,quad} = 0,000847\), \(k_{2,lin} = 0,015558\).
- **Hard**: \(k_{1,quad} = 0,0\), \(k_{2,lin} = 0,051181\). Na medição agregada, a curva do Hard sai côncava e apresenta perda superior à do Medium (ex.: idade 15: \(0,80\text{ s}\) contra \(0,46\text{ s}\)). A explicação de que isso decorre do viés de seleção das pistas (o Hard seria mais usado em circuitos de alta degradação) é uma **hipótese ainda não testada**, que só pode ser confirmada estimando por circuito. Consequentemente, a hierarquia clássica \(\text{Soft} > \text{Medium} > \text{Hard}\) é uma **escolha de modelagem** representada pela vida útil até o cliff.
- **Cliffs (\(a_{cliff}, \Delta_{cliff}, \beta\))**: **Hipótese sem dado empírico** (`cliff: null` no JSON). Como as paradas de box ocorrem antes da falha crítica do composto, um cliff dentro da faixa medida (até 19, 29 e 41 voltas) é contradito pelos dados, enquanto um cliff acima dessa faixa não é confirmado nem descartado. Por isso, a idade do cliff é posicionada acima da última idade medida de cada composto: **Soft** em 25 voltas (\(\Delta=1{,}2\text{ s}, \beta=0{,}9\)), **Medium** em 35 voltas (\(\Delta=0{,}8\text{ s}, \beta=0{,}7\)) e **Hard** em 47 voltas (\(\Delta=0{,}5\text{ s}, \beta=0{,}5\)). Com esses valores, nas últimas idades medidas (19, 29 e 41 voltas, relativas à idade de referência 2) o modelo fornece \(1{,}01\text{ s}\), \(1{,}14\text{ s}\) e \(2{,}02\text{ s}\), todos dentro do IC 95% medido (\(0{,}89 \pm 0{,}46\text{ s}\), \(0{,}97 \pm 0{,}43\text{ s}\) e \(1{,}92 \pm 0{,}42\text{ s}\)).

### 1.4 Referências

- Fieni, G. et al. "Towards Learning-Based Formula 1 Race Strategies" (2025). arXiv:2512.21570 — modelo \(T_{lap} = T_{nom}(\ldots) + \Delta T_j(TW)\) com correção de combustível separada[2].
- "A State-Space Approach to Modeling Tire Degradation in Formula 1 Racing" (2025). arXiv:2512.00640 (stat.AP) — framework bayesiano de espaço de estados usando dados FastF1, com reset de estado em pit stops e degradação específica por composto[3].
- Sulsters et al., "Simulating Formula One Race Strategies" — modelo quadrático de resíduos por composto após remoção do efeito de combustível[4].
- Heilmeier, A. et al. (2020). "Optimal Tyre Management of a Formula One Car" — IFAC 2020, base para \(t_{tire}(a,c) = k_0(c) + k_1(c)\cdot a\)[5].
- F1 Chronicle / Substack — "F1 Tyre Degradation in 2026: The Data Behind the Flipped Hierarchy" (dados agregados de degradação por temporada 2022–2026 a partir de timing oficial)[1].
- Tese de mestrado, Politecnico di Torino — "Probabilistic Simulator for Race Event..." (webthesis.biblio.polito.it/35913) — consolidação dos modelos linear/quadrático e citação de coeficientes McLaren de 0,03 s/kg[6].

---

## 2. Penalidade por Massa de Combustível (Fuel Mass Penalty)

### 2.1 Modelo

Relação linear entre massa de combustível remanescente e tempo de volta, amplamente usada em simuladores de estratégia (Heilmeier, McLaren Applied, Sulsters):

\[
t_{fuel}(l) = \big(m_{fuel,tot} - m_{fuel,consumed}(l)\big) \cdot s_{lap,mass}
\]

Equivalente, para a volta \(l\) de uma corrida com \(N\) voltas e queima linear:

\[
\Delta t_{fuel}(l) = s_{lap,mass} \cdot \dot{m}_{fuel} \cdot (N - l)
\]

### 2.2 Variáveis

| Símbolo | Definição | Unidade |
|---|---|---|
| \(m_{fuel,tot}\) | Massa inicial de combustível embarcado | kg |
| \(m_{fuel,consumed}(l)\) | Combustível consumido até a volta \(l\) | kg |
| \(s_{lap,mass}\) | Sensibilidade empírica do tempo de volta à massa | s/kg |
| \(\dot{m}_{fuel}\) | Taxa média de queima por volta | kg/volta |
| \(N\) | Número total de voltas da corrida | voltas |

### 2.3 Faixas de calibração

- Sensibilidade \(s_{lap,mass}\): consenso da comunidade de engenharia (McLaren Applied Technologies, F1Metrics, Reddit r/F1Technical) situa-se entre 0,03 e 0,08 s/kg, com valor de referência frequentemente citado de 0,03 s/kg (McLaren) e estimativas independentes de ~0,033–0,035 s/kg (1 kg ≈ 30–35 ms)[6][7].
- Combustível máximo regulamentar: 110 kg por corrida desde 2019, mantido no regulamento pós-2022[8][9].
- Consumo real de corrida: tipicamente 95–110 kg totais, com equipes "curtas" de 5–15 kg para ganho de peso quando a margem de fluxo (100 kg/h) permite[10][11].
- Taxa de queima por volta: aproximadamente 1,5–2,0 kg/volta em corridas de ~57–70 voltas (ex.: 110 kg / 57 voltas ≈ 1,93 kg/volta)[12][7].
- Fluxo máximo regulamentar: 100 kg/h (limite técnico da FIA, inalterado na era de efeito solo)[10].

### 2.4 Referências

- Politecnico di Torino, tese de mestrado — formulação de \(t_{fuel}(l)\) atribuída a Heilmeier et al., com coeficiente McLaren de 0,03 s/kg[6].
- Sulsters et al., "Simulating Formula One Race Strategies" — regressão linear \(\tilde{Y}_{it} = \beta_0 + \beta_1 X_{1,it} + e_{it}\) para isolar o efeito de combustível por piloto[4].
- Fieni et al. (2025), arXiv:2512.21570 — separação explícita do termo de combustível do termo de pneu no modelo de tempo de volta[2].
- Red Bull Racing — "Bulls' Guide To: Formula One Fuel" (histórico do limite de 105→110 kg)[9].
- Reddit r/F1Technical — discussão técnica de "Fuel-corrected lap time" com estimativa de 30–35 ms/kg[7].
- Regulamento Técnico FIA (Artigo relativo a fluxo de combustível, 100 kg/h) — citado em múltiplas fontes secundárias técnicas[10].

---

## 3. Efeito de Ar Sujo / Vácuo Turbulento (Aerodynamic Wake / Dirty Air)

### 3.1 Modelo de decaimento de downforce/aderência com o gap

A abordagem consolidada em papers de teoria de jogos aplicada a F1 (2024–2025) modela a redução de downforce e arrasto como função contínua da distância longitudinal (e, em versões estendidas, lateral) ao carro da frente:

\[
D(g) = D_0 \cdot \left[1 - \eta_{wake} \cdot e^{-g/\lambda}\right]
\]

\[
F_{down}(g) = F_{down,0} \cdot \left[1 - \eta_{down} \cdot e^{-g/\lambda}\right]
\]

onde a perda relativa de downforce satura para gaps pequenos e decai exponencialmente com o gap \(g\) (temporal, em segundos, ou espacial, em metros, via \(g_{m} = v \cdot g_{s}\)).

**Perda percentual observada experimentalmente (modelo simplificado por bins de distância):**

\[
\%\Delta F_{down}(g) \approx \%\Delta F_{down,max} \cdot e^{-g/\lambda}
\]

### 3.2 Variáveis

| Símbolo | Definição | Unidade |
|---|---|---|
| \(D(g), D_0\) | Arrasto em esteira / arrasto em ar limpo | N |
| \(F_{down}(g), F_{down,0}\) | Downforce em esteira / downforce em ar limpo | N |
| \(g\) | Gap temporal ou espacial ao carro da frente | s ou m |
| \(\eta_{wake}, \eta_{down}\) | Frações máximas de perturbação de arrasto/downforce | adimensional |
| \(\lambda\) | Constante de decaimento característico da esteira | s ou m |
| \(v\) | Velocidade do carro seguidor | m/s |

### 3.3 Faixas de calibração (regulamento 2022+ de efeito solo)

- Perda de downforce a 1 comprimento de carro: downforce cai de ~680 kgf (ar limpo) para ~390 kgf a 1 car-length, ~310 kgf a 0,5 car-length e ~260 kgf a 0,25 car-length (menos de 40% do pico)[13].
- Perda no front wing especificamente: 30–50% de capacidade de downforce quando em ar sujo[13].
- Penalidade de tempo de volta agregada: 0,35–0,50 s/volta para um carro "colado" a 1 comprimento de carro, dos quais ~65% atribuível a perda de velocidade de curva (não em retas)[14].
- Redução total de downforce integrada (múltiplas zonas): até 12% de perda agregada, com deslocamento do equilíbrio aerodinâmico de 6–8% para trás[14].
- Objetivo regulatório 2022 (efeito solo/underbody): a FIA visou reduzir a sensibilidade a ar sujo em relação à era 2017–2021 de wings de alta carga, mas estudos causais mostram que a penalidade de ar sujo persiste substancialmente mesmo pós-2022[15] — o efeito não foi eliminado, apenas atenuado.
- Testes experimentais em escala (túnel de vento/PIV) mostram perda de downforce de até 53% a distâncias muito curtas (5 cm em modelo reduzido, sem offset lateral), com recuperação rápida ao aumentar distância ou aplicar offset[16].

### 3.4 Referências

- "Game Theory in Formula 1: Multi-agent Physical and ..." (2025). arXiv:2503.05421 — modelo com perda de arrasto e downforce como função da proximidade longitudinal e lateral ao carro líder[17].
- "The Persistence of the Dirty Air Penalty: A Causal Analysis" (2026). arXiv:2608.03192 — análise causal pós-regulamento 2022 de efeito solo, com regressão \(LapTime = \alpha + \beta_1 TyreLife + \beta_2 LapNumber + \varepsilon\) usada para isolar o efeito residual de ar sujo[15].
- "On the Wake Effect and Dirty-air Generation in Formula 1 and High..." — Traffic Engineering journal (lseee.net), com definição formal de dirty air (queda >20% da energia mecânica por unidade de massa relativa ao freestream) e quantificação de 0,35–0,50 s/volta de penalidade[14].
- "Experimental Analysis of Formula 1 Cars Moving Under Wake..." (IJISRT, 2025) — medições experimentais de perda de downforce por distância e offset lateral[16].
- F1 Chronicle — "What Is Dirty Air In F1?" (dados quantitativos de downforce em kg por gap, atribuídos a análises de telemetria/simulação de equipes)[13].

---

## 4. Ganho por DRS (Drag Reduction System)

### 4.1 Modelo de ganho de velocidade e tempo ao longo da zona

O ganho de velocidade terminal com DRS ativo pode ser modelado via balanço de forças longitudinal, com o coeficiente de arrasto reduzido durante a ativação:

\[
F_{drag}(v) = \tfrac{1}{2}\,\rho\,C_D(\delta)\,A\,v^2, \qquad C_D(\delta) = C_{D,closed} - \delta \cdot \Delta C_D
\]

onde \(\delta \in \{0,1\}\) é o estado do DRS (fechado/aberto). A velocidade terminal ao longo da distância \(x\) dentro da zona de ativação de comprimento \(L_{DRS}\) integra a equação de movimento:

\[
m\,\frac{dv}{dt} = F_{trac}(v) - F_{drag}(v,\delta) - F_{roll}
\]

**Ganho de tempo acumulado ao final da zona (aproximação de primeira ordem, DRS ativo por todo \(L_{DRS}\)):**

\[
\Delta t_{DRS} \approx \int_0^{L_{DRS}} \left(\frac{1}{v_{closed}(x)} - \frac{1}{v_{open}(x)}\right) dx
\]

### 4.2 Variáveis

| Símbolo | Definição | Unidade |
|---|---|---|
| \(C_D(\delta)\) | Coeficiente de arrasto (fechado/aberto) | adimensional |
| \(\Delta C_D\) | Redução de \(C_D\) com DRS aberto | adimensional |
| \(\rho\) | Densidade do ar | kg/m³ |
| \(A\) | Área frontal de referência | m² |
| \(v\) | Velocidade instantânea | m/s |
| \(L_{DRS}\) | Extensão da zona de ativação de DRS | m |
| \(\Delta v\) | Ganho de velocidade terminal ao fim da zona | km/h |
| \(\Delta t_{DRS}\) | Ganho de tempo acumulado por volta | s |

### 4.3 Faixas de calibração

- Ganho de velocidade terminal: estimativa oficial da FIA de 10–12 km/h ao final da zona de ativação; fontes técnicas independentes citam faixas mais amplas de 4–5 km/h a 15–20+ km/h dependendo da configuração de asa e do circuito (retas longas como Baku/Monza/Cidade do México apresentam ganhos maiores)[18][19].
- Redução de arrasto: CFD mostra redução de arrasto de ~9,9% a 80 m/s (de 82,1 N para 73,9 N), acompanhada de perda de downforce de ~41,0% (44,6 N → 26,3 N) no mesmo elemento[20].
- Ganho de tempo por volta em qualificação: da ordem de décimos de segundo a ~0,4–0,5 s por zona de DRS em pistas com retas longas (ex.: 0,436 s medido em simulação para Hockenheim)[21].
- Regra de ativação: DRS liberado apenas dentro de zonas definidas quando o gap para o carro da frente é <1,0 s no ponto de detecção; desabilitado nas primeiras voltas/reinícios e em pista molhada[22][23].

### 4.4 Referências

- Wikipedia/FIA — "Drag Reduction System" — estimativa oficial da FIA de ganho de 10–12 km/h no fim da zona[18].
- IEOM Society Proceedings — "CFD Investigation and Performance Analysis of the F1 Drag Reduction System" (2025) — dados quantitativos de redução de arrasto (9,9%) vs. perda de downforce (41,0%) a 80 m/s[20].
- DrRacing's Blog — simulação de ganho de tempo de volta com DRS de 0,436 s em Hockenheim, comparado a resultados reais de pole position[21].
- Monteiro, C.A.B. (2021). "Numerical Study of a Drag Reduction System..." — Universidade Nova de Lisboa (run.unl.pt/bitstream/10362/149236)[24].
- Motorsport.com — "What is DRS in Formula 1 and how does it work?" (regras de ativação: gap <1s, zonas fixas, restrições em safety car/primeiras voltas)[22].

---

## 5. Gerador Estocástico de Acidentes e Falhas

### 5.1 Distribuições probabilísticas recomendadas

**Contagem de incidentes por corrida — Processo de Poisson (homogêneo ou não-homogêneo):**

\[
P(N_{race} = k) = \frac{(\lambda_{race})^k \, e^{-\lambda_{race}}}{k!}
\]

Para heterogeneidade entre corridas/pistos (overdispersion, comum em dados reais de incidentes), recomenda-se **Binomial Negativa** como generalização:

\[
P(N = k) = \binom{k+r-1}{k}\,(1-p)^r\,p^k, \qquad \mathbb{E}[N] = \frac{rp}{1-p}, \quad \text{Var}[N] = \frac{rp}{(1-p)^2}
\]

**Localização espacial do incidente — Processo de Poisson não-homogêneo (NHPP) ao longo do circuito, com taxa \(\lambda(s)\) dependente do setor \(s\):**

\[
\lambda(s) = \lambda_{base} \cdot w_{braking}(s) \cdot w_{grip}(s) \cdot w_{weather}(t)
\]

\[
P(\text{incidente em } [s, s+ds]) = \lambda(s)\, ds
\]

Esta formulação segue diretamente a abordagem de processos de Poisson não-homogêneos aplicados a risco de colisão veicular, com \(\lambda(t)\) derivado da probabilidade instantânea de colisão \(P_{col}(t)\):

\[
\lambda(t) = \frac{P_{col}(t)}{1 - P_{col}(t)}
\]

### 5.2 Ponderação por tipo de setor e consequência (VSC vs. SC)

Modelo hierárquico proposto para o ApexSim:

\[
w_{braking}(s) = 1 + \gamma_1 \cdot \mathbb{1}[\text{zona de frenagem forte}]
\]

\[
P(\text{consequência} = SC \mid \text{incidente}, \text{escapatória}) = \sigma\big(\alpha_0 + \alpha_1 \cdot \mathbb{1}[\text{brita}] + \alpha_2 \cdot v_{impacto}\big)
\]

onde \(\sigma(\cdot)\) é a função logística, mapeando a severidade esperada (maior em escapatórias de brita — carro parado na pista — versus asfalto, onde o carro geralmente retorna sozinho) para a probabilidade de Safety Car pleno em vez de Virtual Safety Car (VSC).

### 5.3 Variáveis

| Símbolo | Definição | Unidade |
|---|---|---|
| \(\lambda_{race}\) | Taxa esperada de incidentes por corrida | incidentes/corrida |
| \(N\) | Número de incidentes observados | contagem |
| \(r, p\) | Parâmetros de forma e probabilidade da Binomial Negativa | adimensional |
| \(\lambda(s)\) | Intensidade de risco no ponto \(s\) do circuito | 1/m |
| \(w_{braking}, w_{grip}, w_{weather}\) | Multiplicadores de risco por zona de frenagem, grip e clima | adimensional |
| \(\gamma_1\) | Fator de amplificação de risco em zona de frenagem forte | adimensional |
| \(\alpha_0, \alpha_1, \alpha_2\) | Coeficientes logísticos de severidade | adimensional |
| \(v_{impacto}\) | Velocidade estimada de impacto | km/h |

### 5.4 Faixas de calibração (dados reais 2021–2022)

- Frequência de Safety Car pleno: 24 deployments na temporada 2022 (22 corridas), vs. 16 em 2021 — aproximadamente 1,0–1,1 SC por corrida em 2022[25].
- Frequência de VSC: 21 deployments em 2022 vs. 10 em 2021 — aproximadamente 0,95 VSC por corrida em 2022, quase o dobro do ano anterior[25].
- Isso sugere \(\lambda_{race}(SC) \approx 1{,}0\text{–}1{,}1\) e \(\lambda_{race}(VSC) \approx 0{,}9\text{–}1{,}0\) como pontos de partida realistas para calibração pós-2022, com forte variância entre circuitos (Mônaco, Bacu e Cingapura historicamente concentram mais incidentes que pistas de alta velocidade como Monza).
- Lista de causas documentadas 2022 (Fandom/F1 Wiki): predominância de "Accident" e "Stranded/beached car" como causas, com duração média de SC pleno de 2–3 voltas e VSC de 0–2 voltas[26].

### 5.5 Referências

- "Probabilistic modelling of car traffic accidents" (2024). arXiv:2410.00446 — processo de contagem com self-excitation para ocorrência temporal de acidentes, base teórica para o processo de Poisson/Hawkes aplicável a incidentes de corrida[27].
- "Probabilistic Collision Risk Estimation through Gauss–Legendre..." arXiv:2507.18819 — formulação de processo de Poisson não-homogêneo \(\lambda(t) = P_{col}(t)/(1-P_{col}(t))\) para risco de colisão, adaptável à intensidade espacial por setor[28].
- Auto Motor und Sport — "F1-Saison 2022: Statistik zu Safety Cars und VSC" (dados oficiais de frequência de SC/VSC 2021 vs. 2022)[25].
- F1 Wiki (Fandom) — "Safety Car" (lista cronológica de deployments de SC e VSC com causa, volta de início/fim)[26].

---

## 6. Modelo Climático Dinâmico (Chuva e Condição de Pista)

### 6.1 Cadeia de Markov discreta para estados de pista

Estados: \(S = \{\text{Seco}, \text{Úmido}, \text{Molhado}\}\). A evolução do estado a cada passo de tempo (ex.: por volta ou por intervalo de 1 min) segue:

\[
\pi_{t+1} = \pi_t \cdot P
\]

onde \(P\) é a matriz de transição estocástica (linhas somam 1):

\[
P = \begin{pmatrix}
p_{SS} & p_{SU} & p_{SM} \\
p_{US} & p_{UU} & p_{UM} \\
p_{MS} & p_{MU} & p_{MM}
\end{pmatrix}
\]

A propriedade de Markov formal (base teórica padrão, consistente com a definição em cursos de processos estocásticos):

\[
P(X_{n+1} = j \mid X_n = i, X_{n-1}, \ldots, X_0) = P(X_{n+1} = j \mid X_n = i) = p_{ij}
\]

Probabilidade de estado após \(k\) passos: \(\pi_{t+k} = \pi_t \cdot P^k\).

### 6.2 Crossover de performance entre compostos

Modelo linear por composto (análogo ao termo de degradação, Seção 1), com tempo de volta em função da severidade de água na pista \(\theta \in [0,1]\) (0 = seco, 1 = encharcado):

\[
t_{lap}(c, \theta) = t_{base}(c) + \kappa(c)\cdot \theta
\]

O **crossover time** entre dois compostos \(c_1, c_2\) é o valor de \(\theta^*\) onde as curvas se cruzam:

\[
\theta^{*} = \frac{t_{base}(c_2) - t_{base}(c_1)}{\kappa(c_1) - \kappa(c_2)}
\]

Isso determina o ponto (em % de água na pista, correlacionável a mm/h de chuva) em que compostos Slick deixam de ser competitivos frente a Intermediários, e Intermediários frente a Full Wet.

### 6.3 Variáveis

| Símbolo | Definição | Unidade |
|---|---|---|
| \(\pi_t\) | Vetor de distribuição de probabilidade sobre estados na etapa \(t\) | adimensional |
| \(P\) | Matriz de transição de Markov | adimensional (probabilidades) |
| \(p_{ij}\) | Probabilidade de transição do estado \(i\) para \(j\) | adimensional |
| \(\theta\) | Severidade de água na pista (proxy contínuo) | adimensional [0,1] |
| \(t_{base}(c)\) | Tempo de volta base do composto \(c\) em pista seca | s |
| \(\kappa(c)\) | Sensibilidade do composto \(c\) à água na pista | s/unidade de \(\theta\) |
| \(\theta^{*}\) | Ponto de crossover entre dois compostos | adimensional |

### 6.4 Faixas de calibração

- Degradação de pneu Wet em chuva forte: penalidade de ritmo de +3,0 s/volta em relação ao composto de referência, com taxa de degradação adicional de ~0,035 s/volta; Intermediário em chuva leve apresenta degradação moderada de ~0,060 s/volta[29].
- Estados operacionais formais no regulamento 2026 (extensível à era pós-2022): pista classificada explicitamente exige uso do "wet-weather tyre" (Full Wet) até que as luzes do Safety Car sejam apagadas, distinguindo formalmente Intermediário de Full Wet como especificações separadas (Art. B6.1.1), com penalidade de stop-and-go para uso incorreto (Art. B6.3.7)[30].
- Não há um limiar oficial de mm/h de chuva publicado pela FIA para troca obrigatória — a decisão é operacional (piloto/equipe/diretor de prova), reforçando a necessidade de um modelo estocástico (Markov) em vez de um limiar determinístico rígido no motor de simulação[30].
- Para calibração inicial sugerida no ApexSim (ausência de matriz FIA publicada — valores de engenharia de simulação, ajustáveis): \(p_{SS}\approx 0{,}90\text{–}0{,}97\), \(p_{UU}\approx 0{,}55\text{–}0{,}70\), \(p_{MM}\approx 0{,}70\text{–}0{,}85\) por passo de 1 volta em cenário de chuva instável, com transições Seco→Molhado direto tipicamente muito baixas (\(p_{SM} < 0{,}02\)), favorecendo caminho via estado Úmido.

### 6.5 Referências

- SFU (Simon Fraser University) — "STAT 380: Markov Chains" (formulação canônica da propriedade de Markov e matriz de transição para estados de clima Seco/Molhado, usada como base didática direta para o modelo do ApexSim)[31].
- "F1 ML Prediction System" (documentação Mintlify) — valores de referência de degradação e ritmo por composto em condições de chuva (TIRE_PACE, TIRE_DEG para WET/INTERMEDIATE)[29].
- SportRules.org — "F1 Wet Weather, Intermediate Tyres, and Standing Start Rules" — citação direta dos artigos regulatórios B6.1.1 e B6.3.7 sobre especificações de pneus de chuva[30].

---

## Notas de Implementação para o Motor de Eventos

- **Ordem de composição do tempo de volta:** recomenda-se a estrutura aditiva \(T_{lap} = T_{nom} + \Delta t_{fuel} + \Delta t_{tire} + \Delta t_{cliff} + \Delta t_{dirtyair} - \Delta t_{DRS} + \Delta t_{clima} + \varepsilon\), com \(\varepsilon \sim \mathcal{N}(0,\sigma^2)\) representando variabilidade residual do piloto, consistente com Sulsters et al.[4] e Fieni et al.[2].
- **Fontes de dados abertos para calibração contínua:** FastF1 (Python API sobre dados oficiais de timing/telemetria da F1) é a fonte primária usada nos papers mais recentes de 2025–2026 (arXiv:2512.00640, arXiv:2608.03192) e deve ser a base de ingestão de dados do ApexSim para recalibração periódica dos coeficientes acima[3][15].
- **Independência de eventos estocásticos:** os módulos de acidente (Seção 5) e clima (Seção 6) devem ser acoplados — \(w_{weather}(t)\) na intensidade de incidentes deve referenciar o estado atual da cadeia de Markov climática, já que pista Úmida/Molhada aumenta materialmente o risco de incidente por perda de aderência.

---

## Referências

[1] F1 Chronicle / Substack — "F1 Tyre Degradation in 2026: The Data Behind the Flipped Hierarchy" (dados agregados de degradação por temporada 2022–2026 a partir de timing oficial).

[2] Fieni, G. et al. "Towards Learning-Based Formula 1 Race Strategies" (2025). arXiv:2512.21570 — modelo \(T_{lap} = T_{nom}(\ldots) + \Delta T_j(TW)\) com correção de combustível separada.

[3] "A State-Space Approach to Modeling Tire Degradation in Formula 1 Racing" (2025). arXiv:2512.00640 (stat.AP) — framework bayesiano de espaço de estados usando dados FastF1, com reset de estado em pit stops e degradação específica por composto.

[4] Sulsters et al., "Simulating Formula One Race Strategies" — modelo quadrático de resíduos por composto após remoção do efeito de combustível.

[5] Heilmeier, A. et al. (2020). "Optimal Tyre Management of a Formula One Car" — IFAC 2020, base para \(t_{tire}(a,c) = k_0(c) + k_1(c)\cdot a\).

[6] Tese de mestrado, Politecnico di Torino — "Probabilistic Simulator for Race Event..." (webthesis.biblio.polito.it/35913) — consolidação dos modelos linear/quadrático e citação de coeficientes McLaren de 0,03 s/kg.

[7] Reddit r/F1Technical — discussão técnica de "Fuel-corrected lap time" com estimativa de 30–35 ms/kg.

[8] Regulamento Técnico FIA — limite de combustível de 110 kg por corrida (vigente desde 2019, mantido no regulamento pós-2022).

[9] Red Bull Racing — "Bulls' Guide To: Formula One Fuel" (histórico do limite de 105→110 kg).

[10] Regulamento Técnico FIA (Artigo relativo a fluxo máximo de combustível, 100 kg/h) — citado em múltiplas fontes secundárias técnicas.

[11] Fontes de engenharia de estratégia (F1Metrics, RaceFans, equipes) — estimativas de consumo real de corrida entre 95–110 kg com estratégia de "short-fueling".

[12] Estimativa derivada de dados de timing oficial (FastF1) — taxa de queima por volta de ~1,5–2,0 kg/volta em corridas de 57–70 voltas.

[13] F1 Chronicle — "What Is Dirty Air In F1?" (dados quantitativos de downforce em kg por gap, atribuídos a análises de telemetria/simulação de equipes).

[14] "On the Wake Effect and Dirty-air Generation in Formula 1 and High..." — Traffic Engineering journal (lseee.net), com definição formal de dirty air (queda >20% da energia mecânica por unidade de massa relativa ao freestream) e quantificação de 0,35–0,50 s/volta de penalidade.

[15] "The Persistence of the Dirty Air Penalty: A Causal Analysis" (2026). arXiv:2608.03192 — análise causal pós-regulamento 2022 de efeito solo, com regressão \(LapTime = \alpha + \beta_1 TyreLife + \beta_2 LapNumber + \varepsilon\) usada para isolar o efeito residual de ar sujo.

[16] "Experimental Analysis of Formula 1 Cars Moving Under Wake..." (IJISRT, 2025) — medições experimentais de perda de downforce por distância e offset lateral.

[17] "Game Theory in Formula 1: Multi-agent Physical and ..." (2025). arXiv:2503.05421 — modelo com perda de arrasto e downforce como função da proximidade longitudinal e lateral ao carro líder.

[18] Wikipedia/FIA — "Drag Reduction System" — estimativa oficial da FIA de ganho de 10–12 km/h no fim da zona.

[19] Fontes técnicas independentes (análises de engenharia, fóruns especializados) — estimativas de ganho de velocidade com DRS em configurações de asa variadas (4–5 km/h a 15–20+ km/h).

[20] IEOM Society Proceedings — "CFD Investigation and Performance Analysis of the F1 Drag Reduction System" (2025) — dados quantitativos de redução de arrasto (9,9%) vs. perda de downforce (41,0%) a 80 m/s.

[21] DrRacing's Blog — simulação de ganho de tempo de volta com DRS de 0,436 s em Hockenheim, comparado a resultados reais de pole position.

[22] Motorsport.com — "What is DRS in Formula 1 and how does it work?" (regras de ativação: gap <1s, zonas fixas, restrições em safety car/primeiras voltas).

[23] Regulamento Esportivo FIA — regras de ativação de DRS (gap <1,0 s no ponto de detecção; desabilitado nas primeiras voltas/reinícios e em pista molhada).

[24] Monteiro, C.A.B. (2021). "Numerical Study of a Drag Reduction System..." — Universidade Nova de Lisboa (run.unl.pt/bitstream/10362/149236).

[25] Auto Motor und Sport — "F1-Saison 2022: Statistik zu Safety Cars und VSC" (dados oficiais de frequência de SC/VSC 2021 vs. 2022).

[26] F1 Wiki (Fandom) — "Safety Car" (lista cronológica de deployments de SC e VSC com causa, volta de início/fim).

[27] "Probabilistic modelling of car traffic accidents" (2024). arXiv:2410.00446 — processo de contagem com self-excitation para ocorrência temporal de acidentes, base teórica para o processo de Poisson/Hawkes aplicável a incidentes de corrida.

[28] "Probabilistic Collision Risk Estimation through Gauss–Legendre..." arXiv:2507.18819 — formulação de processo de Poisson não-homogêneo \(\lambda(t) = P_{col}(t)/(1-P_{col}(t))\) para risco de colisão, adaptável à intensidade espacial por setor.

[29] "F1 ML Prediction System" (documentação Mintlify) — valores de referência de degradação e ritmo por composto em condições de chuva (TIRE_PACE, TIRE_DEG para WET/INTERMEDIATE).

[30] SportRules.org — "F1 Wet Weather, Intermediate Tyres, and Standing Start Rules" — citação direta dos artigos regulatórios B6.1.1 e B6.3.7 sobre especificações de pneus de chuva.

[31] SFU (Simon Fraser University) — "STAT 380: Markov Chains" (formulação canônica da propriedade de Markov e matriz de transição para estados de clima Seco/Molhado, usada como base didática direta para o modelo do ApexSim).
