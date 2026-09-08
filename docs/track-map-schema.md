# 🗺️ Contrato D4: Especificação do Schema do Mapa de Pistas (`track_map`)

Este documento formaliza a especificação de dados do contrato **D4 (Modelagem de Pista Semântica)** para o projeto **ApexSim**. Ele define a estrutura exata do arquivo de dados que será consumido pelo **Motor de Simulação** (Gabriel) e pela **Física & Eventos Estocásticos** (Isaac).

A grande inovação arquitetural adotada é a **desvinculação da simulação física (1D) da renderização visual (2D)**. A pista é modelada semanticamente como um plano linear contínuo, enquanto as representações geométricas $X, Y$ são destinadas exclusivamente ao frontend.

---

## 1. Visão Geral do Modelo

A pista é tratada como um circuito fechado de comprimento linear $L$ em metros (`length_m`). 
1. **Física e Lógica (1D):** O carro possui uma posição de distância acumulada linear (`distance_m`) desde a linha de largada.
2. **Semântica (Zonas em Camadas):** As zonas da pista são intervalos lineares representados como `[start_m, end_m]`. Elas podem se sobrepor em camadas (ex: um trecho de reta pode ser também uma zona de ativação de DRS e pertencer ao Setor 2).
3. **Eventos Pontuais:** Elementos que ocorrem em uma coordenada linear exata (como entrada de box ou detecção de DRS) são descritos como intervalos de largura zero, onde `start_m == end_m`.

---

## 2. Estrutura do Arquivo JSON

Cada circuito deve possuir um arquivo de dados correspondente denominado `track_maps/{circuito}.json`. A estrutura do JSON é composta de três seções principais:

```json
{
  "circuit_id": "string",
  "length_m": "integer",
  "points": [
    { "x": "float", "y": "float", "distance_m": "float" }
  ],
  "zones": [
    {
      "type": "string",
      "start_m": "float",
      "end_m": "float",
      "props": {}
    }
  ]
}
```

### 2.1. Metadados Gerais
*   `circuit_id` *(string, obrigatório)*: Identificador único em minúsculas (ex: `"interlagos"`, `"monza"`, `"monaco"`).
*   `length_m` *(integer, obrigatório)*: Comprimento total oficial da pista em metros de acordo com o regulamento técnico da FIA.

### 2.2. Pontos Geométricos (`points`)
Fornecido pelo Octávio no contrato **D3**. É um array ordenado de cerca de 300 pontos representando o traçado geométrico simplificado.
*   `x` *(float)*: Coordenada cartesiana $X$ relativa (normalizada).
*   `y` *(float)*: Coordenada cartesiana $Y$ relativa (normalizada).
*   `distance_m` *(float)*: Distância linear acumulada desde a linha de largada (metro zero). O último ponto do array deve ter o seu `distance_m` correspondente ao comprimento total oficial (com margem de erro $< 1\%$).

### 2.3. Zonas Semânticas (`zones`)
Array contendo os intervalos de pista anotados. Cada item possui obrigatoriamente as propriedades `type`, `start_m`, `end_m` e `props`.

---

## 3. Tipos de Zona e Propriedades (`props`)

Abaixo estão definidos os **10 tipos de zona homologados** e a especificação de suas respectivas propriedades em `props`:

| Tipo de Zona | Descrição Semântica | Formato Geométrico | Atributos Esperados no Objeto `props` | Consumidor principal |
| :--- | :--- | :--- | :--- | :--- |
| **`sector`** | Um dos 3 setores de cronometragem oficiais do circuito (Setor 1, 2 ou 3). | Intervalo (`start_m < end_m`) | <ul><li>`number` *(integer, [1, 2, 3])*: Identificador do setor.</li></ul> | Motor & Frontend |
| **`corner`** | Curvas oficiais numeradas ou batizadas da pista. | Intervalo (`start_m < end_m`) | <ul><li>`name` *(string)*: Nome oficial (ex: `"S do Senna"`).</li><li>`number` *(integer)*: Número de identificação da curva.</li></ul> | Frontend & Física |
| **`braking_zone`** | Regiões de desaceleração que antecedem as curvas. | Intervalo (`start_m < end_m`) | <ul><li>`severity` *(string, ["baixa", "media", "alta"])*: Força de frenagem exigida.</li><li>`runoff` *(string, ["brita", "asfalto", "muro"])*: Tipo de área de escape (essencial para definir a probabilidade de Safety Car em acidentes).</li></ul> | Física (RNG de acidentes) |
| **`straight`** | Trechos de reta onde o carro atinge aceleração plena. | Intervalo (`start_m < end_m`) | <ul><li>`name` *(string, opcional)*: Ex: `"Reta Oposta"`.</li></ul> | Física & Motor |
| **`drs_detection`** | Ponto de medição do tempo delta de aproximação entre dois competidores. | Ponto (`start_m == end_m`) | N/A *(objeto vazio)* | Física & Motor (Verificar se delta $< 1.0s$) |
| **`drs_activation`** | Zonas onde o DRS pode ser acionado se concedido na detecção. | Intervalo (`start_m < end_m`) | N/A *(objeto vazio)* | Física & Motor |
| **`pit_entry`** | Linha de demarcação de início do pit entry. | Ponto (`start_m == end_m`) | N/A *(objeto vazio)* | Motor (Gatilho para entrar no modo limitador) |
| **`pit_lane`** | Corredor físico dos boxes onde o limite de velocidade é imposto. | Intervalo (`start_m < end_m`) | <ul><li>`speed_limit_kmh` *(integer)*: Velocidade máxima no pitlane (geralmente `80`).</li><li>`time_loss_s` *(float)*: Tempo médio estático gasto para percorrer o pit lane sem contar a troca (ex: `21.5`).</li></ul> | Motor & IA de Estratégia |
| **`pit_exit`** | Linha onde o carro se reintegra à pista de corrida oficial. | Ponto (`start_m == end_m`) | N/A *(objeto vazio)* | Motor (Fim do modo limitador) |
| **`overtaking_spot`** | Pontos propícios para tentativa de ultrapassagem (geralmente ao fim de retas). | Ponto ou Intervalo Curto | <ul><li>`difficulty` *(string, ["baixa", "media", "alta"])*: O quão difícil é efetuar a ultrapassagem naquele local.</li></ul> | Motor (Modulação da chance de ultrapassagem) |

---

## 4. Regras de Validação Rigorosas

Para garantir a integridade da simulação, o script de validação de pista do Daniel (`feature/m1-validation`) deve impor as seguintes restrições lógicas sobre o JSON:

1. **Gerais:**
   * `length_m` deve ser maior que zero.
   * O último ponto em `points` deve possuir `distance_m` igual ou menor a `length_m` (dentro de uma margem de erro razoável de $1\%$).
2. **Limites Espaciais:**
   * Para qualquer zona $i$: $0 \le \text{start\_m}_i \le \text{length\_m}$ e $0 \le \text{end\_m}_i \le \text{length\_m}$.
   * O início do intervalo deve ser menor ou igual ao fim: $\text{start\_m}_i \le \text{end\_m}_i$.
3. **Zonas de Categoria "Ponto":**
   * Se o tipo for `drs_detection`, `pit_entry`, ou `pit_exit`, a validação DEVE exigir que $\text{start\_m} == \text{end\_m}$.
4. **Zonas Contínuas (Não Sobreponíveis internamente):**
   * **Setores:** Não podem se sobrepor entre si e devem cobrir a totalidade da pista. $\sum (\text{end\_m}_k - \text{start\_m}_k) == \text{length\_m}$.
   * **Pit Lane:** Não pode haver mais de uma zona `pit_lane` ativa no mesmo espaço linear.

---

## 5. Exemplo de JSON de Referência (Interlagos)

Abaixo está um modelo representativo contendo as marcações semânticas que o editor de pista irá gerar para Interlagos:

```json
{
  "circuit_id": "interlagos",
  "length_m": 4309,
  "points": [
    { "x": 100.0, "y": 500.0, "distance_m": 0.0 },
    { "x": 105.2, "y": 501.1, "distance_m": 5.3 },
    { "x": 110.8, "y": 503.2, "distance_m": 11.2 },
    { "x": 98.5,  "y": 499.8, "distance_m": 4308.5 }
  ],
  "zones": [
    {
      "type": "sector",
      "start_m": 0,
      "end_m": 1200,
      "props": { "number": 1 }
    },
    {
      "type": "sector",
      "start_m": 1200,
      "end_m": 3100,
      "props": { "number": 2 }
    },
    {
      "type": "sector",
      "start_m": 3100,
      "end_m": 4309,
      "props": { "number": 3 }
    },
    {
      "type": "corner",
      "start_m": 3980,
      "end_m": 4180,
      "props": { "name": "S do Senna", "number": 1 }
    },
    {
      "type": "braking_zone",
      "start_m": 3880,
      "end_m": 3980,
      "props": { "severity": "alta", "runoff": "brita" }
    },
    {
      "type": "drs_detection",
      "start_m": 3850,
      "end_m": 3850,
      "props": {}
    },
    {
      "type": "drs_activation",
      "start_m": 4180,
      "end_m": 4309,
      "props": {}
    },
    {
      "type": "pit_entry",
      "start_m": 4120,
      "end_m": 4120,
      "props": {}
    },
    {
      "type": "pit_lane",
      "start_m": 4120,
      "end_m": 4309,
      "props": { "speed_limit_kmh": 80, "time_loss_s": 18.5 }
    },
    {
      "type": "pit_exit",
      "start_m": 350,
      "end_m": 350,
      "props": {}
    },
    {
      "type": "overtaking_spot",
      "start_m": 3980,
      "end_m": 4020,
      "props": { "difficulty": "baixa" }
    }
  ]
}
```
