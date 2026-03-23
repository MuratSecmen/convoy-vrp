# convoy-vrp

**Bi-Objective Military Convoy Vehicle Routing Problem**
**Deterministik + Stokastik Model — ISAF/IJC CJ4 Surface Movement**

---

## Modeller

### 1. BCMC-VRPHD — Deterministik

**Bi-Objective Capacitated Military Convoy VRP with Heterogeneous Demand**

| | |
|---|---|
| **f₁ = W₁** | min max_k L_k — en yavaş konvoy seyahat süresi |
| **f₂ = W₂** | min max_k (L_k − L̄_k) / L̄_k — plan sapması |

Özellikler: Açık tur · MCNF alt tur eleme · 6 NATO ikmal sınıfı · İki katmanlı araç gözlemlenebilirliği · Erken varış yasağı · ε-constraint Pareto cephesi

### 2. S-BCMC-VRPHD — Stokastik

**Two-Stage Stochastic Bi-Objective Min-Max Military Convoy VRP**

| | |
|---|---|
| **Stage-1** | Sabah brifinginde rota planı — senaryo bağımsız |
| **Stage-2** | Konvoy yoldayken recourse — senaryo gerçekleşince |

6 ISAF Afganistan senaryosu:

| ω | Tip | p_ω | δ | κ |
|---|---|---|---|---|
| ω₁ | Nominal | 0.217 | 1.00 | 0.0 |
| ω₂ | Güney MSR kapanması | 0.196 | 1.10 | 0.2 |
| ω₃ | Doğu MSR kapanması | 0.152 | 1.00 | 0.1 |
| ω₄ | Talep artışı | 0.152 | 1.35 | 0.0 |
| ω₅ | ROE kısıtı | 0.130 | 1.00 | 1.0 |
| ω₆ | Bileşik aksaklık | 0.152 | 1.20 | 0.5 |

---

## Referanslar

- Yakıcı & Karasakal (2013). *Optimization Letters* 7(7), 1611–1625.
- Karasakal et al. (2011). *Naval Research Logistics* 58, 305–322.
- Silav et al. (2021). *Annals of OR* 311(2), 1229–1247.
- Birge & Louveaux (1997). *Introduction to Stochastic Programming*.
- Bektaş & Gouveia (2014). *EJOR* 236(3), 820–832.
- Haimes et al. (1971). *IEEE Trans. SMC* SMC-1(3), 296–297.
- NATO CFC Counter-IED Report (2013).

---

## Proje Yapısı

```
convoy-vrp/
├── src/
│   ├── deterministic_model.py   # BCMC-VRPHD solver
│   ├── stochastic_model.py      # S-BCMC-VRPHD solver
│   ├── loader_det.py            # Deterministik Excel yükleyici
│   ├── loader_stoch.py          # Stokastik Excel yükleyici
│   └── export.py                # Pareto → Excel + JSON
├── data/
│   ├── generate_det_instances.py    # Deterministik benchmark üretici
│   ├── generate_stoch_instances.py  # Stokastik benchmark üretici
│   └── instances/
│       ├── small_n5_k3.xlsx         # Det: 5 düğüm, 3 araç
│       ├── medium_n10_k5.xlsx       # Det: 10 düğüm, 5 araç
│       ├── large_n15_k7.xlsx        # Det: 15 düğüm, 7 araç
│       ├── small_stoch_n5_k3.xlsx   # Stoch: 5 düğüm, 3 araç, 6 senaryo
│       ├── medium_stoch_n10_k5.xlsx # Stoch: 10 düğüm, 5 araç, 6 senaryo
│       └── large_stoch_n15_k7.xlsx  # Stoch: 15 düğüm, 7 araç, 6 senaryo
├── tests/
│   ├── test_deterministic.py
│   └── test_stochastic.py
├── results/
├── main.py
├── requirements.txt
└── README.md
```

---

## Kurulum

```bash
pip install -r requirements.txt
```

Python 3.9+ gerektirir.

---

## Kullanım

**Instance üretimi:**
```bash
python data/generate_det_instances.py    # deterministik
python data/generate_stoch_instances.py  # stokastik
```

**Deterministik çözüm:**
```bash
python main.py --mode det --instance data/instances/small_n5_k3.xlsx
python main.py --mode det --all
```

**Stokastik çözüm:**
```bash
python main.py --mode stoch --instance data/instances/small_stoch_n5_k3.xlsx
python main.py --mode stoch --all
```

**Seçenekler:**
```
--mode        det veya stoch
--instance    .xlsx dosya yolu
--n_points    Pareto nokta sayısı (varsayılan: 10)
--time_limit  MIP çözücü zaman sınırı, saniye (varsayılan: 300)
--verbose     CBC solver çıktısını göster
--all         Klasördeki tüm uygun instanceları çalıştır
```

---

## Deterministik Excel Formatı (7 sheet)

| Sheet | Anahtar sütunlar |
|---|---|
| Nodes | node_id, type, x_km, y_km |
| Vehicles | vehicle_id, platform, capacity_tonnes, observable |
| TravelTime | from, to, vehicle_id, time_min |
| Demand | node_id, class, quantity |
| ServiceRate | vehicle_id, class, rate |
| Baseline | vehicle_id, baseline_min |
| Regions | node_id, ao_region |

## Stokastik Excel Formatı (10 sheet — 3 ek sheet)

Deterministik sheetslerine ek olarak:

| Sheet | İçerik |
|---|---|
| Scenarios | omega_id, label, probability, delta, kappa |
| BlockedArcs | omega_id, from, to |
| CongestionMultipliers | omega_id, from, to, vehicle_id, mu |

---

## Testler

```bash
python -m pytest tests/ -v
```

---

## Çıktılar

`results/` klasörüne kaydedilir:
- Deterministik: `*_det_pareto.xlsx` — Pareto tablosu, rotalar, servis süreleri
- Stokastik: `*_stoch_pareto.json` — Pareto noktaları + VSS değeri

Knee point (operasyonel tercih noktası) Excel çıktısında amber rengiyle işaretlenir.
