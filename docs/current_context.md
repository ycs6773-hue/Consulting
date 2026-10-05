# Current Context — HFSS 2.4 GHz Patch Antenna 의뢰

- 의뢰처: insight.cae@gmail.com / 수신 2026-10-04 / 계획 승인: 추천안 전체 (Q1~Q9)
- 현재 Phase: **P1~P3 완료 → P4(사용자 PC 실행) 대기**

## Phase 현황
| Phase | 내용 | 상태 |
|---|---|---|
| P1 | PyAEDT HFSS 자동화 스크립트 (`hfss_patch/`) | ✅ 완료 (AEDT 실행 검증은 사용자 PC 필요) |
| P2 | 해석적 계산 모듈 + 단위 테스트 (`analytic.py`) | ✅ 완료 (Balanis 예제 일치) |
| P3 | 결과 후처리 + Word 리포트 (`postprocess/plots/report.py`) | ✅ 완료 (synthetic 데이터로 검증) |
| P4 | 사용자 PC 실행 → 보고서 완성 → 고객 회신 초안 | ⏳ 대기 |

## P1 산출물
- `hfss_patch/config.py` — YAML 로드/타입/물리 검증 (λ0/4 이격, inset < L, 포트 크기 등)
- `hfss_patch/geometry.py` — 설계 변수 표현식 기반 형상 정의 + 안전한 수치 평가 + 위상 검사
- `hfss_patch/builder.py` — Hfss(Modal) 모델링 → PerfE/Radiation/Wave Port → Setup/Sweep/FF sphere
  → Parametric(L, y0, gap) → 해석 → CSV export → release_desktop (finally)
- `hfss_patch/run.py` — CLI (`--dry-run`, `--no-parametric`, `--no-solve`, `--version`, `--cores`)
- `tests/` — 64개 (config/geometry, fake Hfss 세션 해제, analytic, 후처리/보고서)

## P2/P3 산출물
- `analytic.py` — TL 모델(G1/G12 적분, inset y0, Hammerstad Wf, BW 추정). `python -m hfss_patch.analytic --f0 2.4 --er 4.4 --h 1.6`
- `postprocess.py` — PyAEDT CSV(';', 단위 헤더) 파서, S11/BW/ISM 판정, E/H cut·HPBW·F/B·XPD, 파라메트릭 요약, L 튜닝값
- `plots.py` — 형상도, S11, Smith, 2D 패턴, 3D 맵, 파라메트릭 그림
- `report.py` — metrics.json + Word 보고서(한국어, 판정표/권고 자동 생성). synthetic 데이터면 헤더 워터마크
- `synthetic.py` — 미리보기/테스트 전용 가짜 결과 + 캡처 placeholder (납품 금지)
- `capture.py` — 해석 후 저장된 .aedt를 **graphical 모드로 재오픈**해 캡처 6종 (모델 iso/top, |Jsurf|, 기판 중간면 |E|,
  3D Polar 패턴, S11 리포트) → `results/.../captures/*.jpg` + `captures.json`. 항목별 실패 격리, finally에서 release_desktop

## 사용자 PC 실행 절차 (Windows, AEDT 2025.1 기준)
```
pip install -r requirements.txt
python -m pytest -q
python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml --dry-run
python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml --no-solve   # 모델만 생성 → GUI로 형상 확인
python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml              # 해석 + Parametric + export
python -m hfss_patch.report --config hfss_patch/configs/patch_2g4_fr4.yaml --customer insight.cae@gmail.com
python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml --capture-only   # 캡처만 재실행
```
- 캡처는 YAML `capture.enabled`(기본 true) 또는 `--capture/--no-capture`. `--no-solve` 실행에는 캡처 없음
- 캡처 실행 시 AEDT GUI 창이 뜸 → **화면 켜진 상태**로 실행 (RDP 잠금/최소화 시 검은 이미지 위험)
- 산출물: `results/patch_2g4_fr4/` (.aedt, s11.csv, farfield_*.csv, antenna_params.csv,
  s11_param_*.csv, convergence.prop, mesh_stats.ms, run_summary.json, logs/)
- Exit code: 0 OK / 1 해석 실패 / 2 설정·형상 오류 / 3 PyAEDT 없음 / 4 일부 export·캡처 실패 (결과는 사용 가능)

## 대안 비교안 (RO4003C 60 mil) — `configs/patch_2g4_ro4003c.yaml`
- εr 3.55(Rogers 설계 Dk), tanδ 0.0027, h 1.524 / W 41.40, L 32.74, y0 11.90, Wf 3.44, 기판 75×85 mm
- 해석식 예측: 효율 ≈ 86 %, Gain ≈ 6 dBi(목표 충족) / -10 dB BW ≈ 31 MHz(FR-4보다 **좁음**) → ISM 전대역은 여전히 미달
- 실행: 동일 절차로 `--config .../patch_2g4_ro4003c.yaml` 실행 후
  `python -m hfss_patch.report --config .../patch_2g4_fr4.yaml --compare .../patch_2g4_ro4003c.yaml` → 보고서 8장 비교

## ⚠️ 사양 리스크 (해석식/합성 모델 기반 예측 — HFSS로 확정 필요)
- FR-4 1.6 mm 단일 패치: -10 dB BW 예상 ≈ 55~60 MHz < ISM 83.5 MHz → Q3 'ISM 전대역' 미달 가능성 높음
- 방사 효율 ≈ 45 % (tanδ 0.02) → Peak Gain ≈ 3 dBi < 목표 4 dBi 가능성
- 저손실 기판은 이득만 해결(대역폭은 감소). ISM 전대역은 공기/폼 기판·적층 패치·U-slot 구조 변경 필요 — 고객 협의

## 미검증 리스크 (첫 실행 시 확인)
- wave port 적분선 문자열 좌표("-Lsub/2" 등) 처리 여부
- "Antenna Parameters" 카테고리 표현식명(PeakGain 등) — AEDT 버전별 차이 가능
- 캡처: Mag_Jsurf/Mag_E 수량명, 3D Polar Plot 리포트, cut plane 'h/2' 수식이 실제 AEDT에서 동작하는지
- Parametric 3종 × 순차 해석 시간 (L 7점 + y0 6점 + gap 3점 = 16 variation)
