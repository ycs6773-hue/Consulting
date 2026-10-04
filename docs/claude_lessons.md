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
