# Current Context — HFSS 2.4 GHz Patch Antenna 의뢰

- 의뢰처: insight.cae@gmail.com / 수신 2026-10-04 / 계획 승인: 추천안 전체 (Q1~Q9)
- 현재 Phase: **P1 완료 → P2 대기**

## Phase 현황
| Phase | 내용 | 상태 |
|---|---|---|
| P1 | PyAEDT HFSS 자동화 스크립트 (`hfss_patch/`) | ✅ 완료 (AEDT 실행 검증은 사용자 PC 필요) |
| P2 | 해석적 계산 모듈 + 단위 테스트 | ⏳ 대기 |
| P3 | 결과 후처리 + Word 리포트 생성기 | ⏳ 대기 |
| P4 | 사용자 PC 실행 → 보고서 완성 → 고객 회신 초안 | ⏳ 대기 |

## P1 산출물
- `hfss_patch/config.py` — YAML 로드/타입/물리 검증 (λ0/4 이격, inset < L, 포트 크기 등)
- `hfss_patch/geometry.py` — 설계 변수 표현식 기반 형상 정의 + 안전한 수치 평가 + 위상 검사
- `hfss_patch/builder.py` — Hfss(Modal) 모델링 → PerfE/Radiation/Wave Port → Setup/Sweep/FF sphere
  → Parametric(L, y0, gap) → 해석 → CSV export → release_desktop (finally)
- `hfss_patch/run.py` — CLI (`--dry-run`, `--no-parametric`, `--no-solve`, `--version`, `--cores`)
- `tests/` — 23개 (config/geometry, fake Hfss 기반 세션 해제·실패 격리)

## 사용자 PC 실행 절차 (Windows, AEDT 2025.1 기준)
```
pip install -r requirements.txt
python -m pytest -q
python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml --dry-run
python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml --no-solve   # 모델만 생성 → GUI로 형상 확인
python -m hfss_patch.run --config hfss_patch/configs/patch_2g4_fr4.yaml              # 해석 + Parametric + export
```
- 산출물: `results/patch_2g4_fr4/` (.aedt, s11.csv, farfield_*.csv, antenna_params.csv,
  s11_param_*.csv, convergence.prop, mesh_stats.ms, run_summary.json, logs/)
- Exit code: 0 OK / 1 해석 실패 / 2 설정·형상 오류 / 3 PyAEDT 없음 / 4 일부 export 실패

## 미검증 리스크 (첫 실행 시 확인)
- wave port 적분선 문자열 좌표("-Lsub/2" 등) 처리 여부
- "Antenna Parameters" 카테고리 표현식명(PeakGain 등) — AEDT 버전별 차이 가능
- Parametric 3종 × 순차 해석 시간 (L 7점 + y0 6점 + gap 3점 = 16 variation)
