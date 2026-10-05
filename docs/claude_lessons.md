# Claude Lessons — 오류/교훈/주의사항

## 2026-10-04 — P1 (HFSS patch 자동화)

### L1. 방사 경계 이격은 스윕 **최저 주파수** 기준
- 계획서 초안은 λ0/4 ≈ 31 mm(@2.4 GHz)로 잡았으나, 스윕이 2.0 GHz부터이므로 λ0/4 = 37.5 mm.
- `config.validate`가 이를 검출 → air = 38 mm로 수정. 이격 검증은 항상 sweep_start 기준.

### L2. PyAEDT 최신 API 시그니처 변경 주의 (ansys-aedt-core, 2026-10 main 기준 확인)
- `insert_infinite_sphere`: `x_start/y_start` → `phi_start/theta_start` 등으로 변경됨.
- `create_box(origin, sizes)`, `create_rectangle(orientation, origin, sizes)` (구 `position/dimensions_list`).
- `Hfss(version=..., project=..., design=...)` (구 `specified_version/projectname`).
- `parametrics.add(...)`는 setup+sweep(nominal_sweep)이 먼저 있어야 함 → setup 이후 생성.
- `validate_simple()`은 bool이 아니라 int(1/0) 반환.

### L3. XZ/YZ 평면 rectangle의 sizes 축 순서는 모호 → 포트 시트는 3D 좌표 polyline으로 생성
- `create_polyline(points, cover_surface=True, close_surface=True)` 사용 — 좌표가 명시적.

### L4. finally 블록에서 2차 예외가 1차 예외를 덮어쓰지 않게
- `run_summary.json` 쓰기, `save_project`, `release_desktop`을 각각 try/except로 감싸고 로그만 남김.
- `json.dumps(default=str)`로 PyAEDT 반환 객체 직렬화 실패 방지.

### L5. stage 래퍼는 내부 HfssJobError도 stage 이름으로 다시 감쌀 것
- 그렇지 않으면 "design validation returned None"처럼 어느 단계인지 로그에서 추적 불가.

### L6. 환경 제약
- 클라우드 컨테이너: PyPI에서 ansys-aedt-core 설치 불가(네트워크 정책), GitHub 소스 clone은 가능.
  → API 검증은 소스 sparse checkout으로 수행, 실행 검증은 fake Hfss(MagicMock) 테스트로 대체.

## 2026-10-04 — P2/P3

### L7. 패치 edge 저항은 G1 근사식(W/120λ0) 쓰지 말 것
- W≈0.3λ0에서는 W≪λ0 근사가 깨짐: 근사 197 Ω vs 적분 G1+G12 321 Ω → y0 9.8 → 10.9 mm.
- analytic.py는 Balanis 예제 14.1/14.3과 테스트로 고정 (회귀 방지).

### L8. E/H-plane은 급전 방향이 결정
- 급전이 y축 → E-plane = yz = φ 90°, H-plane = φ 0°. 계획서 초안의 φ=0 E-plane은 오류였음.
- θ 0–180 cut 하나는 반쪽 → φ와 φ+180을 합쳐 −180..180 full cut으로 만들어야 HPBW/F/B 계산 가능.

### L9. 사양 판정은 숫자로 먼저 확인 — "ISM 전대역 -10 dB" 목표는 FR-4 1.6 mm로 비현실적
- 무손실 VSWR2 BW 1.1 %, 손실 포함 Q≈28 → -10 dB BW ≈ 56 MHz < 83.5 MHz. 효율 ≈ 44 %.
- 승인 기준이라도 물리적으로 미달 예상이면 해석 전 사용자에게 즉시 보고.

### L10. 테스트 기대값도 손계산으로 검증
- notch BW 71.6 MHz를 ISM pass로 잘못 기대 → 판정 로직이 맞았음. 기대값을 먼저 의심하되 근거 계산으로 확정.

### L11. 환경: 이 컨테이너의 soffice는 모든 파일 변환 실패("source file could not be loaded")
- docx 렌더 검증 대신: python-docx 재로딩 + 텍스트 추출 + 그림 PNG 직접 확인.
- python-docx 기본 템플릿의 settings.xml w:zoom percent 누락은 XSD 경고일 뿐 Word 열기에는 문제 없음.

## 2026-10-05 — 캡처 단계

### L12. AEDT 화면 캡처는 graphical 세션 필수 → 해석과 분리
- `export_model_picture`, `FieldPlot.export_image`는 docstring상 graphical 모드에서만 동작.
- 해석은 non-graphical 유지, 캡처는 저장된 .aedt를 `non_graphical=False, remove_lock=True`로 재오픈하는 별도 단계.
- 캡처 실패가 해석 성공을 덮지 않도록: 항목별 try, 오픈 실패도 해석 후라면 exit 4(부분 실패)로 처리.
- `export_report_to_jpg(path, plot_name)`: path가 디렉터리가 아니면 그대로 파일명으로 사용됨 → 전체 경로 전달.
- `create_fieldplot_*`의 `field_type`은 Q3D 전용 — HFSS에서는 무시됨.

### L13. 보고서 그림 번호는 하드코딩 금지
- 선택적 그림(캡처)이 끼면 번호가 어긋남 → `_Figures` 카운터로 실제 삽입된 그림만 순번 부여.

## 2026-10-05 — RO4003C 비교안

### L14. "저손실 기판 = 대역폭 개선"은 틀림 — 권고 전 Q 계산으로 확인
- 같은 두께에서 tanδ 0.02→0.0027이면 Q 28→52, -10 dB BW 57→31 MHz(감소), 효율 44→86 %(증가).
- FR-4의 넓은 대역은 손실(Qd=1/tanδ) 덕분. 이전 보고서 권고 문구가 이를 거꾸로 서술 → 정정 + 회귀 테스트 추가.
- 대역폭 확보는 h/λ0 증가(공기/폼 기판), 적층 패치, U-slot 등 구조 변경으로만 가능.
- RO4003C 시뮬레이션 εr은 Rogers 권장 design Dk 3.55 (process Dk 3.38 아님).

### L15. 비교 보고서는 한쪽이라도 synthetic이면 전체 워터마크
