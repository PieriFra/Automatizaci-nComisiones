# ----------------------------------------------------------------------------------------------
# Diccionario de clientes por empresa
# Cada empresa tiene su propio diccionario {cliente: vendedor}
# Un mismo cliente puede aparecer en ambas empresas con el mismo o distinto vendedor.
# ----------------------------------------------------------------------------------------------

# ── Di Pascuale (DP) ──────────────────────────────────────────────────────────
MAPA_CLIENTES_DP  = {
    "AGUILAR CRISTIAN FABIAN Y NOCENTI SERGIO HERNAN": "FRAIRE",
    "ARNAUDO MATIAS GONZALO": "FRAIRE",
    "AVERSA FACUNDO": "GIUSTA",
    "BARCO SEBASTIAN FERNANDO": "GIUSTA",
    "BALVERDI RAUL ALEJANDRO": "FRAIRE",
    "BRACO Y PORTA SA": "FRAIRE",
    "BURSZTYN GERARDO DANIEL": "GIUSTA",
    "CHIAVERANO GORGO SANTIAGO": "GIUSTA",
    "CAVALLERO DIEGO ALBERTO": "FRAIRE",
    "CRESPO ANGELO MATÍAS": "FRAIRE",
    "CONDE JESICA ELIZABETH": "ALARCÓN",
    "DAVID ROSENTAL E HIJOS": "FRAIRE",
    "DEAN GUILLERMO HORACIO": "ALARCÓN",
    "DISTRIBUIDORA OGGIER SRL": "FRAIRE",
    "ELZAP S.R.L": "FRAIRE",
    "FANG MEIJIN": "GIUSTA",
    "FABIAN ALFREDO FACCIOLI": "FRAIRE",
    "FERREYRA REBECA RUTH": "FRAIRE",
    "GAGLIANO MARIA EMILIA Y GAGLIANO NICOLAS LUIS": "FRAIRE",
    "Gagliano Maria Emilia y Gagliano Nicolas": "FRAIRE",
    "GENERO ZUNILDA ISABEL NORMA": "FRAIRE",
    "GIRARDI WALTER ANTONIO": "FRAIRE",
    "GONZALES MATÍAS FEDERICO": "ALARCÓN",
    "HUANG XIAOMEI": "GIUSTA",
    "HUANG ZHI": "GIUSTA",
    "INOCENTI CARLOS": "GIUSTA",
    "LIN XUEMEI": "GIUSTA",
    "LISI CESAR AUGUSTO": "ALARCÓN",
    "MANUEL SANTIAGO": "GIUSTA",
    "MORONI LEANDRO OSCAR": "GIUSTA",
    "PADUAN CAROLINA BEATRIZ": "FRAIRE",
    "PERSOGLIA GONZALO EDUARDO": "FRAIRE",
    "PROVINCIAS UNIDAS COOPERATIVA DE PROVISION PARA COMERCIANTES DE VIVIENDA Y CREDITO LIMITADA": "FRAIRE",
    "RED VITAL AGRUPACIÓN": "FRAIRE",
    "SAN JAVIER DISTRIBUIDORA DE ALIMENTOS S.R.L.": "FRAIRE",
    "SFP SA": "GIUSTA",
    "TOLOZA JUAN RAMON": "GIUSTA",
    "VACA DANIEL JAVIER": "FRAIRE",
    "VARGAS FIGUEROA SANTIAGO ALBERTO": "GIUSTA",
    "WANG FENGLAN": "GIUSTA",
    "WANG JINSHAN": "GIUSTA",
    "WENG ZHIHUI": "GIUSTA",
    "WUANG LU": "GIUSTA",
    "YACCUZZI DISTRIBUCIONES SRL": "FRAIRE",
    "ZHENG YUANGONG": "GIUSTA"
}

# ── Fills ─────────────────────────────────────────────────────────────────────
MAPA_CLIENTES_FILLS = {
    "AGUILAR CRISTIAN FABIAN Y NOCENTI SERGIO HERNAN": "FRAIRE",
    "ARNAUDO MATIAS GONZALO": "FRAIRE",
    "AVERSA FACUNDO": "GIUSTA",
    "BARCO SEBASTIAN FERNANDO": "GIUSTA",
    "BALVERDI RAUL ALEJANDRO": "FRAIRE",
    "BRACO Y PORTA SA": "FRAIRE",
    "BURSZTYN GERARDO DANIEL": "GIUSTA",
    "CHIAVERANO GORGO SANTIAGO": "GIUSTA",
    "CAVALLERO DIEGO ALBERTO": "FRAIRE",
    "CRESPO ANGELO MATÍAS": "FRAIRE",
    "CONDE JESICA ELIZABETH": "ALARCÓN",
    "DAVID ROSENTAL E HIJOS": "FRAIRE",
    "DEAN GUILLERMO HORACIO": "ALARCÓN",
    "DISTRIBUIDORA OGGIER SRL": "FRAIRE",
    "ELZAP S.R.L": "FRAIRE",
    "FANG MEIJIN": "GIUSTA",
    "FABIAN ALFREDO FACCIOLI": "FRAIRE",
    "FERREYRA REBECA RUTH": "FRAIRE",
    "GAGLIANO MARIA EMILIA Y GAGLIANO NICOLAS LUIS": "FRAIRE",
    "GENERO ZUNILDA ISABEL NORMA": "FRAIRE",
    "GIRARDI WALTER ANTONIO": "FRAIRE",
    "GONZALES MATÍAS FEDERICO": "ALARCÓN",
    "HUANG XIAOMEI": "GIUSTA",
    "HUANG ZHI": "GIUSTA",
    "INOCENTI CARLOS": "GIUSTA",
    "LIN XUEMEI": "GIUSTA",
    "LISI CESAR AUGUSTO": "ALARCÓN",
    "MANUEL SANTIAGO": "GIUSTA",
    "MORONI LEANDRO OSCAR": "GIUSTA",
    "PADUAN CAROLINA BEATRIZ": "FRAIRE",
    "PERSOGLIA GONZALO EDUARDO": "FRAIRE",
    "PROVINCIAS UNIDAS COOPERATIVA DE PROVISION PARA COMERCIANTES DE VIVIENDA Y CREDITO LIMITADA": "FRAIRE",
    "RED VITAL AGRUPACIÓN": "FRAIRE",
    "SAN JAVIER DISTRIBUIDORA DE ALIMENTOS S.R.L.": "FRAIRE",
    "SFP SA": "GIUSTA",
    "TOLOZA JUAN RAMON": "GIUSTA",
    "VACA DANIEL JAVIER": "FRAIRE",
    "VARGAS FIGUEROA SANTIAGO ALBERTO": "GIUSTA",
    "WANG FENGLAN": "GIUSTA",
    "WANG JINSHAN": "GIUSTA",
    "WENG ZHIHUI": "GIUSTA",
    "WUANG LU": "GIUSTA",
    "YACCUZZI DISTRIBUCIONES SRL": "FRAIRE",
    "ZHENG YUANGONG": "GIUSTA"
}

# Alias para compatibilidad con código anterior
MAPA_CLIENTES_VENDEDORES = MAPA_CLIENTES_DP
 
# ---------------------------------------------------------------------------
# Clientes con reglas de comisión especiales (por empresa)
# ---------------------------------------------------------------------------
# Si un cliente aparece acá, se le aplica el porcentaje indicado en lugar
# del porcentaje estándar del vendedor.
# Estructura: { empresa: { nombre_cliente_normalizado: { beneficiario: porcentaje } } }
 
REGLAS_ESPECIALES = {
    "DP": {
        "DAVID ROSENTAL E HIJOS": {"FRAIRE": 0.05},
    },
    "FILLS": {},
}
 
# ---------------------------------------------------------------------------
# Reglas de comisión estándar por empresa y vendedor
# ---------------------------------------------------------------------------
 
REGLAS_COMISION = {
    "DP": {
        "FRAIRE":  {"FRAIRE": 0.08},
        "GIUSTA":  {"GIUSTA": 0.05, "FRAIRE": 0.03},
        "ALARCON": {"ALARCON": 0.04, "FRAIRE": 0.04},
    },
    "FILLS": {
        "FRAIRE":  {"FRAIRE": 0.06},
        "GIUSTA":  {"GIUSTA": 0.04, "FRAIRE": 0.02},
        "ALARCON": {"ALARCON": 0.03, "FRAIRE": 0.03},
    },
}