# CNN 기반 RC카 자율주행

ESP32-CAM의 영상을 PC에서 받아 `left`, `straight`, `right` 세 방향으로
분류하고, Raspberry Pi Pico에 조향 명령을 보내는 교육용 자율주행
프로젝트입니다. 수동 주행 데이터 수집, CNN 학습, 모의 예측, 실제 차량
주행까지 한 폴더에서 실행할 수 있습니다.

> 실제 차량을 시험할 때는 먼저 바퀴를 지면에서 띄우고 동작을 확인하세요.
> 카메라나 PC 통신이 끊겨도 차량이 멈추는 감시 기능이 있지만, 주변 안전을
> 확보하고 즉시 전원을 차단할 수 있는 상태에서 시험해야 합니다.

## 주요 기능

- PyQt5 조이스틱 UI를 이용한 RC카 수동 조종
- 주행 중 `left`, `straight`, `right` 이미지 자동 분류 및 저장
- 밝기·대비 증강과 클래스 가중치를 적용한 CNN 학습
- 카메라 영상 위에 방향별 예측 확률 표시
- 낮은 예측 신뢰도와 추론 지연 시 자동 정지
- PC 제어 신호가 1초 이상 끊기면 Pico에서 비상 정지

## 동작 구조

```text
ESP32-CAM ──MJPEG──> PC
                       ├─ 01.drive.py       데이터 수집
                       ├─ 02.train_cnn.py   CNN 학습
                       └─ 03.ai_drive.py    실시간 추론
                                │
                                └─UART/Serial──> Raspberry Pi Pico ──> 모터·조향
```

## 파일 구성

| 파일 | 설명 |
| --- | --- |
| `01.drive.py` | 수동 조종 및 학습 데이터 수집 |
| `02.train_cnn.py` | 데이터 분할, CNN 학습, 평가 결과 저장 |
| `03.ai_drive.py` | 실시간 영상 추론 및 자율주행 |
| `04.serial_steering_test.py` | 카메라 없이 시리얼 조향 시험 |
| `ai_common.py` | 클래스, 영상 크기, 카메라 방향 공통 설정 |
| `myjoystickcamapp.py` | 카메라·조이스틱·수집 GUI |
| `main.py` | Pico용 차량 제어 및 통신 감시 코드 |
| `_Config.py` | Pico 핀 번호와 하드웨어 설정 |
| `05.genai_object.py` | 수업용 사진 인식 연출 예제(자율주행과 독립) |
| `00.CNN_자율주행_사용법.md` | 간단한 자율주행 실행 안내 |

`camera.py`, `myjoystick*.py`, `test.py`는 카메라와 조이스틱 UI를 단계별로
실습한 예제입니다.

## 준비물

- Python 3.10 또는 3.11 권장
- Raspberry Pi Pico와 MicroPython
- ESP32-CAM MJPEG 스트림
- USB 또는 Bluetooth 시리얼 연결
- 프로젝트 하드웨어에 맞는 모터, 조향 서보, 센서

### Pico 의존 파일

현재 폴더의 `main.py`는 다음 Pico용 모듈도 사용합니다.

- `_Oled.py`
- `_VehicleLights.py`

`_ServoMotor.py`는 포함되어 있지만 위 두 파일은 현재 프로젝트 폴더에 없습니다.
실제 Pico에서 사용 중인 동일한 버전의 모듈과 OLED 드라이버가 있다면 Pico에
함께 업로드해야 합니다. PC에서 데이터 수집·학습·모의 예측만 할 때는 필요하지
않습니다.

## PC 설치

가상환경을 만든 뒤 의존성을 설치합니다.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

TensorFlow 설치가 지원되는 Python 버전인지 먼저 확인하세요. 시리얼 포트와
카메라 주소의 기본값은 각각 `COM6`, `http://192.168.4.1:81/stream`입니다.

## 1. 데이터 수집

Pico에서 `main.py`를 실행하고 다음 명령으로 조종 화면을 엽니다.

```powershell
python 01.drive.py
```

장치 설정이 다르면 실행 옵션으로 지정할 수 있습니다.

```powershell
python 01.drive.py --port COM7 --camera http://192.168.4.1:81/stream
```

수집 결과는 기본적으로 아래 구조로 저장됩니다.

```text
dataset/
└─ session_YYYYMMDD_HHMMSS_mmm/
   ├─ left/
   ├─ straight/
   ├─ right/
   └─ labels.csv
```

연속된 비슷한 프레임 수보다 조건의 다양성이 중요합니다. 서로 다른 조명,
곡률, 차량 위치에서 여러 세션으로 나누어 수집하고 세 클래스가 지나치게
불균형하지 않도록 맞추는 것을 권장합니다.

## 2. CNN 학습

```powershell
python 02.train_cnn.py
```

주요 옵션은 다음과 같습니다.

```powershell
python 02.train_cnn.py --dataset dataset --epochs 40 --batch-size 32
```

학습 산출물은 `trained_model/`에 생성됩니다.

- `model.keras`: 최종 모델
- `best_model.keras`: 검증 성능이 가장 좋았던 모델
- `model_metadata.json`: 클래스와 영상 전처리 설정
- `test_metrics.json`: 시험 정확도와 클래스별 지표
- `confusion_matrix.*`: 혼동행렬
- `training_history.*`: 학습 곡선

이 폴더와 `dataset/`은 생성 데이터이므로 Git에는 포함되지 않습니다.

## 3. 차량을 움직이지 않고 예측 확인

```powershell
python 03.ai_drive.py --no-serial
```

화면에서 `LEFT`, `STRAIGHT`, `RIGHT` 확률이 카메라 위치에 따라 자연스럽게
바뀌는지 확인합니다. 이 모드에서는 차량 명령을 보내지 않습니다.

## 4. 실제 자율주행

Pico의 `main.py`를 먼저 실행한 뒤 PC에서 다음 명령을 실행합니다.

```powershell
python 03.ai_drive.py --port COM6
```

| 키 | 기능 |
| --- | --- |
| `A` | 자율주행 시작 |
| `Space` | 브레이크 및 일시정지 |
| `Q` / `E` | 왼쪽 / 오른쪽 방향지시등 |
| `H` | 비상등 |
| `0` | 방향지시등 끄기 |
| `Esc` | 비상정지 후 종료 |

기본 예측 신뢰도 기준은 `0.52`이며 필요하면 변경할 수 있습니다.

```powershell
python 03.ai_drive.py --confidence 0.60 --debug-serial
```

## 현재 모델 참고 결과

기존 모델은 총 3,764장(`left` 1,236장, `straight` 2,271장,
`right` 257장)으로 학습했으며 기록된 시험 정확도는 약 **88.9%**입니다.
다만 연속 프레임을 무작위로 나눈 결과이고 우회전 표본도 적으므로, 실제 코스
성능을 그대로 의미하지 않습니다. 별도 주행 세션을 학습에서 제외해 최종
검증하는 것을 권장합니다.

## 설정 변경

카메라가 거꾸로 보이거나 좌우가 반대라면 `ai_common.py`의 다음 값을
수집과 추론에서 동일하게 사용해야 합니다.

```python
CAMERA_ROTATION_DEGREES = 180
CAMERA_MIRROR_HORIZONTAL = True
```

조향 각도와 Pico 핀 번호는 `_Drive.py`, `_Config.py`에서 차량에 맞게
조정합니다.

## 저장소에 포함하지 않는 항목

- `dataset/`: 촬영 이미지와 라벨
- `trained_model/`: 학습 모델과 평가 산출물
- `api/key.env`, `.env*`: API 키 등 민감정보
- `.venv/`, `__pycache__/`: 로컬 Python 환경과 캐시

API 키나 개인 경로가 포함된 파일은 커밋하지 마세요.
