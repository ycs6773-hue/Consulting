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
