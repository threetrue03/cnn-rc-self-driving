# CNN RC카 자율주행

ESP32-CAM 영상과 Raspberry Pi Pico를 이용한 교육용 RC카 프로젝트입니다. PC에서 방향키로 차량을 조종하며 영상을 수집하고, `left`·`straight`·`right` 3개 클래스로 CNN을 학습한 뒤 실시간 영상으로 조향합니다. 전진, 조향, 브레이크, 방향지시등은 각각 별도의 명령으로 제어합니다.

> 현재는 새 카메라로 데이터를 다시 수집하는 단계입니다. 이전 카메라로 만든 데이터와 `trained_model/`의 모델은 실제 주행 성능을 검증한 결과가 아닙니다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `01.drive.py` | 수동 조종과 데이터 수집 |
| `myjoystickcamapp.py` | 카메라 화면·키 입력·이미지 저장 UI |
| `02.train_cnn.py` | 3분류 CNN 학습과 평가 |
| `03.ai_drive.py` | MJPEG 영상 수신, 예측, Pico 조향 명령 |
| `04.serial_steering_test.py` | 모터를 정지한 채 좌·중앙·우 조향 검사 |
| `ai_common.py` | 클래스 순서와 추론용 카메라 변환 설정 |
| `main.py`, `_*.py` | Pico의 모터·서보·센서·조명 제어 |

흐름: `ESP32-CAM → PC의 수집/추론 프로그램 → 시리얼 → Pico → 모터·서보·네오픽셀`

`05.genai_object.py`와 그 사용법 문서는 자율주행과 별개인 수업 예제입니다.

## 준비

- PC: Python, ESP32-CAM 스트림에 연결할 수 있는 네트워크, Pico 시리얼 연결
- 차량: Raspberry Pi Pico, ESP32-CAM, 모터, 조향 서보, 네오픽셀 및 프로젝트의 센서
- Pico 파일: `main.py`, `_Config.py`, `_Drive.py`, `_ServoMotor.py`, `_Battery.py`, `_DistanceSensor.py`, `_Oled.py`, `_VehicleLights.py` 등 실제 차량에서 사용하는 모듈

현재 이 저장소에는 `_Oled.py`와 `_VehicleLights.py`가 없습니다. Pico에 이미 업로드된 동일 버전의 파일이 있어야 `main.py`가 실행됩니다. 해당 파일 없이 새 Pico를 설정할 수는 없습니다.

PowerShell에서 프로젝트 폴더로 이동한 뒤 PC 패키지를 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

기본 카메라 주소는 `http://192.168.4.1:81/stream`, 기본 시리얼 포트는 `COM6`입니다. 실제 연결에 맞게 실행 옵션을 바꿔주세요. 수동 조종 프로그램과 자율주행 프로그램을 동시에 실행하면 같은 시리얼 포트를 사용할 수 없습니다.

## 1. 카메라 확인과 데이터 수집

새 카메라를 장착한 뒤 먼저 수동 조종 화면에서 차선이 올바른 방향으로 보이는지 확인합니다.

```powershell
python 01.drive.py --port COM6 --camera http://192.168.4.1:81/stream
```

| 키 | 수동 조종 |
| --- | --- |
| `↑` / `↓` | 전진 / 후진 |
| `←` / `→` | 핸들 왼쪽 / 오른쪽 |
| `Space` | 브레이크 |
| `Q` / `E` | 왼쪽 / 오른쪽 방향지시등 |
| `H` / `0` | 비상등 / 방향지시등 끄기 |
| `F5` | 데이터 수집 시작 / 종료 |

수집 영상은 전진 중이고 브레이크를 밟지 않았을 때 `dataset/session_.../{left,straight,right}/`에 저장됩니다. 현재 수집 프로그램은 저장 전에 이미지를 `160×120`으로 줄입니다. 첫 수집에서는 수십 장만 저장한 뒤 JPG를 직접 열어 방향, 선명도, 라벨을 확인하세요. 새 카메라 데이터는 이전 카메라의 데이터와 섞지 않는 편이 좋습니다.

가능하면 시계·반시계 방향으로 여러 세션을 수집하고, 직진뿐 아니라 좌우 회전과 차선에서 벗어났다가 복구하는 장면도 포함하세요. 클래스별 장수가 비슷하도록 수집 화면의 개수를 확인합니다.

## 2. CNN 학습

```powershell
python 02.train_cnn.py --dataset dataset --output trained_model
```

학습이 끝나면 `trained_model/model.keras`, `model_metadata.json`, `test_metrics.json`, 혼동행렬과 학습 그래프가 생성됩니다. 전체 정확도 외에 좌·직진·우 각각의 재현율을 확인하세요. 연속 촬영 프레임을 무작위로 분할한 시험 점수는 실제 코스 주행 성능보다 높게 나올 수 있습니다. 새 주행 세션으로 별도 시험하는 것이 좋습니다.

## 3. 조향과 예측 확인

바퀴를 지면에서 띄우고 Pico의 서보가 좌·중앙·우로 움직이는지 확인합니다.

```powershell
python 04.serial_steering_test.py --port COM6
```

차량 명령 없이 카메라 예측만 보려면 다음 명령을 사용합니다.

```powershell
python 03.ai_drive.py --no-serial
```

화면에서 예측 방향이 카메라 위치에 맞게 바뀌는지 확인합니다. `03.ai_drive.py`의 기본 모델 경로는 `trained_model/model.keras`입니다.

## 4. 자율주행

수집 프로그램을 종료하고 Pico에서 `main.py`를 실행한 다음 PC에서 시작합니다.

```powershell
python 03.ai_drive.py --port COM6 --debug-serial
```

| 키 | 자율주행 화면 |
| --- | --- |
| `A` | 자율주행 시작 |
| `Space` | 브레이크 및 일시정지 |
| `Q` / `E` | 왼쪽 / 오른쪽 방향지시등 |
| `H` / `0` | 비상등 / 방향지시등 끄기 |
| `Esc` | 비상정지 후 종료 |

CNN은 조향만 `left → <`, `straight → |`, `right → >`로 결정합니다. 전진 `F`, 정지 `S`, 브레이크 `B/b`는 별도로 전송합니다. 예측 확률이 기본 기준 `0.52`보다 낮거나 추론이 오래 멈추면 PC가 차량을 정지시킵니다. Pico의 통신 감시 기능도 자율주행 중 제어 신호가 끊기면 정지하도록 설계돼 있습니다. 첫 실제 시험은 바퀴를 띄운 상태에서 하세요.

## 카메라 방향 주의

현재 `myjoystickcamapp.py`의 수집 경로는 카메라 원본 프레임을 그대로 저장합니다. 반면 `ai_common.py`에는 추론 기본값으로 180도 회전과 좌우 반전이 설정돼 있습니다. 새 카메라로 재수집할 때 두 화면의 방향이 같아야 하며, 방향이 다르면 `ai_common.py`의 `CAMERA_ROTATION_DEGREES`와 `CAMERA_MIRROR_HORIZONTAL`을 수집 영상에 맞게 조정하고 다시 학습해야 합니다. 방향 설정을 바꾼 뒤에는 `--no-serial`로 확인하세요.
