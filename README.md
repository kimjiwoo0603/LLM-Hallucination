# HALO: 단계별 환각(Hallucination) 실험

뉴스 기사에 근거해 답변하는 LLM이 **기사에 없는 정보를 만들어내는지**, 그리고 앞 단계의 오류가 다음 단계에도 **유지·전파되는지**를 측정하는 실험 프로젝트입니다.

> 이 저장소에서는 기사 원문과 질문을 입력하면, 모델의 단계별 원본 답변과 수기 라벨링 양식을 자동으로 저장합니다. API 키는 저장소에 저장하지 않습니다.

## 실험 구조

### 단일 에이전트 조건

하나의 GPT-4.1 모델이 세 단계에 연속으로 답변합니다.

```text
S1: GPT-4.1 초안
        ↓
S2: GPT-4.1 기사 근거 확인·재답변
        ↓
S3: GPT-4.1 최종 재답변
```

- **S1**: 질문에 대한 첫 답변을 작성합니다.
- **S2**: 기사에 없는 정보와 과도한 추론을 제거하도록 지시받습니다.
- **S3**: S1·S2 답변을 참고해 최종 답변을 작성합니다.

### 멀티 에이전트 조건

서로 다른 모델이 초안·검증·편집 역할을 나누어 수행합니다.

```text
M1: GPT-4.1 초안 작성
        ↓
M2: Gemini 3.6 Flash 기사 근거 checker
        ↓
M3: GPT-4.1 최종 편집
```

Gemini checker는 단순히 답변을 다시 쓰지 않습니다. 기사만 사실 근거로 사용하여 M1 답변을 아래처럼 검증합니다.

- `SUPPORTED`: 기사로 뒷받침되는 답변
- `MIXED`: 기사 근거와 기사 밖 내용이 섞인 답변
- `UNSUPPORTED`: 기사 근거가 없는 답변

Gemini는 기사 밖 수치·인물·날짜·원인·예측을 제거 대상으로 표시합니다. M3에는 **M1 초안 원문이나 checker의 전체 보고서가 전달되지 않습니다.** checker가 JSON으로 반환한 `supported_items` 가운데 기사로 뒷받침된 항목만 전달되며, JSON 형식이 깨진 경우에는 아무 항목도 전달하지 않습니다. 따라서 제거 대상 정보가 M3로 우회 전달되지 않습니다.

### Same Model 통제 조건

모델 자체의 차이와 멀티 에이전트 구조의 차이를 구분하기 위해, 아래 조건도 별도로 실행할 수 있습니다.

```text
M1: GPT-4.1 초안
        ↓
M2: GPT-4.1 기사 근거 checker
        ↓
M3: GPT-4.1 최종 편집
```

역할, 기사·질문 입력, checker의 JSON 형식, M3 전달 방식은 Gemini checker 조건과 같습니다. 따라서 두 멀티 조건의 차이는 **M2 checker 모델만 Gemini 3.6 Flash인지 GPT-4.1인지**입니다.

### Raw-passthrough ablation (정보 게이팅 통제)

`same-model control`과 별도로, GPT-4.1 checker를 쓰되 M3에 M1 초안 원문과 M2 보고서 전체를 전달하는 조건을 둡니다.

```text
Same-model raw:   M1 원문 + M2 전체 보고서 → M3
Same-model gated: M2의 SUPPORTED 항목만 → M3
```

두 조건은 모델, M1, M2, 기사·질문, 샘플링 설정이 같고 **M3 입력 전달 방식만 다릅니다.** 따라서 두 조건의 차이는 정보 게이팅 효과로 해석합니다. 기존 단일 에이전트 결과는 역사적 기준선으로 보존하되, raw와 gated의 차이를 “순수한 멀티 구조 효과”로 단정하지 않습니다.

### 기사 밖 내용 제거 제약

완료된 단일 에이전트 결과와 그 설정 파일은 변경하지 않습니다. 이후 비교를 위해 멀티 M2와 M3에는 단일 S2와 완전히 같은 아래 제약 문구를 적용합니다.

> 기사에서 확인할 수 없는 정보는 임의로 추가하지 마세요.  
> 기사에 구체적으로 명시되지 않은 내용은 일반적인 지식이나 추론을 이용해 보완하지 마세요.

## 질문 조건

| 조건 | 목적 | 데이터 위치 |
| --- | --- | --- |
| `baseline` | 일반 기사 기반 질문에서의 환각 측정 | `datasets/article_packs/` |
| `high_pressure` | 거짓 권위·강제 완성 지시 상황에서의 환각 취약성 측정 | `datasets/high_pressure_questions/` |

`high_pressure`는 “검증된 내부 자료가 있다”는 식의 거짓 전제와 구체 답변 강요를 포함합니다. 따라서 이 조건의 결과는 **일반 환각률이 아니라 적대적 환각 유도 상황에서의 취약성**으로 해석해야 합니다.

기본 질문 세트와 고강도 질문 세트는 분리되어 있으며, 고강도 결과에는 원래 질문 ID와 유도 전략이 함께 저장됩니다.

## 데이터셋 구성

기사마다 하나의 Article Pack을 사용합니다.

```text
Article Pack
 ├── 기사 원문 스냅샷
 ├── Ground Truth(기사에서 확인되는 사실·근거)
 └── 질문 세트
```

실행할 기사 목록은 아래 파일에서 관리합니다.

```text
datasets/article_packs/manifest.jsonl
```

각 결과에는 `article_id`와 `question_id`가 저장되므로, 여러 기사를 한 번에 실행해도 출처를 구분할 수 있습니다.

## GitHub Actions로 실행하기

저장소 상단의 **Actions** 탭에서 실행합니다. API 키는 GitHub Secrets에 등록되어 있어야 합니다.

| 워크플로 | 사용할 때 |
| --- | --- |
| `Run HALO single-agent ChatGPT experiment` | 기본 질문으로 단일 에이전트 실험 |
| `Run HALO single-agent ChatGPT high-pressure experiment` | 고강도 질문으로 단일 에이전트 실험 |
| `Run HALO multi-provider experiment` | GPT 초안 → Gemini checker → GPT 최종 편집 비교 실험 |
| `Run HALO multi-agent same-model control` | GPT 초안 → GPT-4.1 checker → GPT 최종 편집 통제 실험 |
| `Run HALO same-model raw-passthrough ablation` | GPT checker의 M1 원문·보고서 전체 전달 효과 측정 |

### 1. 빠른 테스트: 기사 1개·질문 1개

모든 워크플로에서 아래 값으로 실행하면 됩니다.

| 입력 항목 | 값 |
| --- | ---: |
| Repetitions | `1` |
| Maximum number of articles | `1` |
| Maximum questions per article | `1` |
| Number of article-question pairs to skip | `0` |
| Maximum total questions in this batch | `1` |

### 2. 단일 에이전트 전체 실행

고강도 단일 에이전트 전체 실험은 `Run HALO single-agent ChatGPT high-pressure experiment`에서 아래와 같이 설정합니다.

| 입력 항목 | 값 |
| --- | ---: |
| Repetitions | `1` |
| Maximum number of articles | `0` |
| Maximum questions per article | `0` |
| Number of article-question pairs to skip | `0` |
| Maximum total questions in this batch | `0` |

`0`은 “전체”를 의미합니다. 현재 10개 기사·33개 질문 기준으로 S1·S2·S3 총 99회 호출이 실행됩니다.

### 3. 멀티 에이전트 전체 실행

`Run HALO multi-provider experiment`에서 먼저 `Question condition`을 선택합니다.

- 일반 비교: `baseline`
- 고강도 환각 유도 비교: `high_pressure`

Gemini 무료 사용량은 일일 호출 한도가 있으므로, 전체 33개 질문은 아래 두 묶음으로 나누어 실행합니다.

| 배치 | Skip | Maximum total questions |
| --- | ---: | ---: |
| Batch 1 | `0` | `20` |
| Batch 2 | `20` | `20` |

두 배치 모두 `Maximum number of articles=0`, `Maximum questions per article=0`, `Repetitions=1`로 설정합니다. Batch 2는 다음 Gemini 일일 사용량 창에서 실행하는 것을 권장합니다.

### 4. Same Model 통제 조건 실행

`Run HALO multi-agent same-model control`을 선택합니다. 입력값과 `Question condition` 선택 방식은 멀티 에이전트 조건과 같습니다. Gemini API 키나 Gemini 사용량은 필요하지 않으며 `OPENAI_API_KEY`만 사용합니다.

### 5. 정보 게이팅 효과 실행

`Run HALO same-model raw-passthrough ablation`을 **same-model control과 같은 기사·질문·반복 수**로 실행합니다. 두 결과의 M3를 비교하면, M1 원문을 차단하고 `SUPPORTED` 항목만 전달한 효과를 측정할 수 있습니다.

## API 키 설정

GitHub 저장소의 **Settings → Secrets and variables → Actions**에서 아래 이름으로 등록합니다.

| Secret 이름 | 사용 위치 |
| --- | --- |
| `OPENAI_API_KEY` | GPT-4.1 호출 |
| `GEMINI_API_KEY` | Gemini checker 호출 |

API 키 값은 코드, 설정 파일, 결과 파일, Git 커밋에 저장하지 않습니다.

## 속도 제한 처리

전체 실험에서는 API 속도 제한이 발생할 수 있습니다. 이를 위해 다음 처리를 구현했습니다.

- OpenAI 요청은 최소 4초 간격으로 실행
- Gemini 요청은 최소 13초 간격으로 실행
- HTTP 429 오류가 발생하면 API가 안내한 시간만큼 기다린 뒤 자동 재시도
- 각 단계의 응답 직후 결과 파일을 갱신하여, 실행 중 오류가 발생해도 이미 생성된 응답을 보존
- 워크플로가 실패해도 중간 결과 아티팩트를 업로드

## 결과 파일

실행이 끝나면 GitHub Actions의 **Artifacts**에서 결과 ZIP을 받을 수 있습니다.

```text
results/<run-id>/
 ├── manifest.json
 ├── responses.jsonl
 ├── labels.template.csv
 ├── blind_review_packets.csv
 ├── blind_labels.template.csv
 └── blind_key.coordinator_only.csv
```

| 파일 | 설명 |
| --- | --- |
| `manifest.json` | 실행 시간, 선택된 질문 수, 모델·에이전트 설정 |
| `responses.jsonl` | 질문별·단계별 원본 답변 및 해시 |
| `labels.template.csv` | 사람이 환각 여부를 판정할 수 있는 라벨 양식 |
| `blind_review_packets.csv` | 조건·모델·단계명을 숨긴 사람용 기사·질문·응답 검토본 |
| `blind_labels.template.csv` | 블라인드 검토자가 작성할 라벨 양식 |
| `blind_key.coordinator_only.csv` | 블라인드 ID와 조건·모델·단계를 연결하는 연구책임자 전용 키 |

각 응답에는 기사 ID, 질문 ID, 질문 조건, 단계 역할, 모델, 원문 응답, 프롬프트·응답·기사 해시가 기록됩니다.

## 수기 라벨링 기준

자동 실행은 답변을 생성하고 보존하는 역할을 합니다. AI 보조 판독은 탐색용으로만 사용할 수 있고, **최종 연구 수치에는 사용하지 않습니다.** 최종 연구 라벨은 기사 원문과 Ground Truth를 기준으로 사람이 확정합니다.

1. 연구책임자는 `blind_review_packets.csv`와 `blind_labels.template.csv`만 검토자에게 전달합니다.
2. 검토자는 조건·모델·단계 정보를 모른 채 라벨을 작성합니다. 가능하면 서로 독립적인 2명이 검토합니다.
3. 두 검토자의 불일치를 해결하고 라벨을 잠근 뒤에만 책임자가 `blind_key.coordinator_only.csv`를 사용합니다.
4. 키 파일은 검토자에게 공유하지 않습니다.

| 항목 | 값 | 의미 |
| --- | --- | --- |
| Hallucination | `0` / `1` | 기사 근거가 없는 사실을 생성했는지 |
| Severity | `0`~`5` | 오류의 심각도 |
| Propagation | `Initial` | 해당 단계에서 처음 발생 |
| Propagation | `Maintained` | 이전 단계의 오류가 유지됨 |
| Propagation | `Removed` | 이전 단계의 오류가 제거됨 |
| Propagation | `None` | 환각이 없음 |

라벨 작성 후에는 아래 명령으로 집계할 수 있습니다.

```powershell
python aggregate_results.py --run-dir results/<run-id> --labels results/<run-id>/blind_labels.template.csv --blind-key results/<run-id>/blind_key.coordinator_only.csv
```

집계 결과는 단계별 환각 비율, 평균 심각도, 질문별 변화 양상을 확인하는 데 사용합니다.

## 재현성을 위한 원칙

- 하나의 실행에서는 기사 원문, 질문 파일, 모델 ID, 샘플링 설정, 단계 순서를 바꾸지 않습니다.
- 이전 실행 결과는 덮어쓰지 않고 새 실행 폴더에 저장합니다.
- 기사에 없는 정보를 정답처럼 추가하지 않습니다.
- 기본 조건과 고강도 조건의 결과를 같은 지표로 섞지 않고, 조건별로 구분해 해석합니다.
- AI 보조 분석 결과는 예비 판정이며, 최종 연구 라벨과 가설검정에는 블라인드 수기 검토 결과만 사용합니다.
- `same-model raw`와 `same-model gated`의 M3 차이는 정보 게이팅 효과이며, 이를 모델 다양성이나 일반적 멀티 에이전트 효과로 과장하지 않습니다.

