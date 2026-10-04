# Plan — HFSS 해석 의뢰: 2.4 GHz 패치 안테나 설계/해석

- 의뢰처: insight.cae@gmail.com (2026-10-04 수신, 제목 "HFSS 해석 의뢰")
- 요구사항(원문): "HFSS로 2.4GHz에서 공진하는 패치안테나 설계 후 해석, 결과 보고서 전달"
- 첨부/사양서: 없음 → 기판·급전·성능 목표 미지정 (아래 질문 리스트로 확정)
- 상태: **승인 완료(2026-10-04, 추천안 전체)** — P1 완료, 진행 상황은 docs/current_context.md

## 1. 초기 설계안 (가정: FR-4, εr=4.4, tanδ=0.02, h=1.6 mm, 35 µm Cu)

전송선로 모델(Balanis) 기반 1차 치수 — HFSS 파라메트릭 스윕으로 최종 튜닝 예정.

| 항목 | 값 | 비고 |
|---|---|---|
| Patch W | 38.0 mm | c/(2f)·√(2/(εr+1)) |
| ε_eff | 4.086 | |
| ΔL (fringing) | 0.74 mm | Hammerstad |
| Patch L | 29.4 mm | 공진 길이 (해석 후 ±1 mm 튜닝) |
| Edge R_in | ≈321 Ω | G1+G12 적분식 (P2에서 정정, 초안 197 Ω은 근사식 오류) |
| Inset 깊이 y0 | ≈10.9 mm | 50 Ω 매칭, 스윕 8–13 mm |
| Inset gap | 1.0 mm | 스윕 대상 |
| 50 Ω Feed 폭 | ≈3.0 mm | FR-4 1.6 mm microstrip |
| GND/기판 크기 | ≈70 × 80 mm | 패치 + 6h 이상 여유, ~λ0/2 |

## 2. 해석 셋업 (HFSS, PyAEDT `Hfss` 객체 기반)

1. Solution type: Modal (Driven Modal)
2. Geometry: Substrate(box) / GND(sheet, PerfE 또는 finite cond.) / Patch+Inset+Feed(sheet)
3. Excitation: Wave Port (기판 엣지, 폭 ≈ 6~10×Wf, 높이 ≈ 6h) — 대안 Lumped Port
4. Boundary: Radiation box (스윕 최저 2.0 GHz 기준 λ0/4 = 37.5 mm → 38 mm 이격)
5. Setup: Adaptive @2.4 GHz, MaxDeltaS 0.02, Max passes 15
6. Sweep: Interpolating 2.0–2.8 GHz, 1 MHz step
7. Optimetrics: L(28–31 mm), y0(7–12 mm), gap(0.5–1.5 mm) Parametric
8. 세션 관리: `non_graphical=True` → 해석/리포트 export → `hfss.release_desktop(close_projects=True, close_desktop=True)` (try/finally 보장)

## 3. 결과 산출물 (보고서 항목)

- S11 (dB) / 공진 주파수 / -10 dB 대역폭
- 입력 임피던스 (Smith chart), VSWR
- 2D 방사패턴 (급전 y축 → E-plane φ=90°, H-plane φ=0°), 3D Gain
- Peak Gain / Directivity / 방사효율 / 교차편파(XPD)
- E-field / Surface current 분포
- 수렴 이력(Adaptive passes, ΔS), 메쉬 통계 → 재현성 근거
- 최종 치수 도면 + 파라메트릭 민감도 표
- 산출 형식: Word(.docx) 보고서 + .aedt 프로젝트 + PyAEDT 스크립트

## 4. 실행 환경 제약 (중요)

- 현재 작업 환경(클라우드 Linux 컨테이너)에는 **AEDT/HFSS 및 라이선스 없음** → HFSS 솔버 실행 불가
- 제안 분담:
  - (A) 본 세션: PyAEDT 자동화 스크립트(모델링→해석→결과 export→Word 리포트) + 해석적 사전 검증
  - (B) 사용자 Windows 워크스테이션(라이선스 보유): 스크립트 실행 → 결과 CSV/이미지 회수
  - (C) 본 세션: 결과 판정·보고서 완성 → 고객 회신 메일 초안 작성(발송은 사용자 승인 후)
- 선택 옵션: openEMS(오픈소스 FDTD)로 Linux에서 사전 교차검증 — 고객 요구는 HFSS이므로 보고서 본 결과로는 미사용

## 5. 질문 리스트 (추천안 포함) — 승인 시 확정

| # | 질문 | 추천 |
|---|---|---|
| Q1 | 기판 재질/두께? | **FR-4 εr 4.4, 1.6 mm** (사양 미지정 시 업계 표준). RF 성능 중시면 Rogers RO4003C 0.813 mm |
| Q2 | 급전 방식? | **Inset microstrip feed** (단층, 제작 용이) / 대안: coax probe |
| Q3 | 성능 목표? | **S11 ≤ -10 dB @2.400–2.4835 GHz(ISM 전대역)**, Gain ≥ 4 dBi(FR-4 현실치) |
| Q4 | 편파? | **선형 편파** (원편파 요구 시 truncated-corner 추가 설계) |
| Q5 | 크기 제약/GND 크기? | 제약 없음 가정, **70×80 mm** |
| Q6 | 포트 방식? | **Wave Port** (Lumped Port 대비 임피던스 정의 명확) |
| Q7 | 실행 방식? | **(A)+(B)+(C) 분담** — 스크립트는 본 세션 작성, HFSS 실행은 사용자 PC |
| Q8 | 고객에 사양 확인 메일 먼저 보낼지? | **가정사항 명시 후 바로 진행**, 보고서에 "Assumptions" 섹션 기재 (필요 시 확인 메일 초안 작성) |
| Q9 | 산출물 형식/납기? | **Word 보고서 + .aedt + 스크립트**, 납기는 사용자 확정 |

## 6. 작업 Phase (승인 후)

- P1 ✅: `hfss_patch/` PyAEDT 스크립트 (설계 파라미터 YAML, 로깅, 예외 처리, release_desktop 보장)
- P2 ✅: 해석적 계산 모듈 + 단위 테스트 (초기치 재현성)
- P3 ✅: 결과 후처리 + Word 리포트 생성기 (python-docx)
- P4: 사용자 PC 실행 → 결과 반영 → 보고서 완성 → 고객 회신 초안
