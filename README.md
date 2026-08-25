# HALO: Staged Hallucination Experiment

이 저장소는 **Single-Agent와 Multi-Model 조건에서 Hallucination이 어떻게 발생하고, 이후 단계에서 유지되거나 제거되는지 평가하기 위한 실험 코드**입니다.

Single-Agent 실험은 하나의 모델이 다음과 같이 3단계로 답변을 생성합니다.

```text
SINGLE_STAGE_1 → SINGLE_STAGE_2 → SINGLE_STAGE_3
```

각 질문과 반복 실행마다 **S1, S2, S3의 원본 답변**을 저장하며, 실험 재현을 위해 사용한 **프롬프트, 모델 설정, 기사 원문**에 대한 정보도 함께 기록합니다.

### Pilot 질문

Pilot 실험에서는 다음 6개 질문을 사용합니다.

> `Q005`, `Q009`, `Q011`, `Q012`, `Q013`, `Q014`

---

## 🔒 실험에서 고정되는 조건

동일한 실험(run)에서는 다음 조건을 변경하지 않습니다.

| 항목          | 내용                     |
| ----------- | ---------------------- |
| 📄 Article  | 실험에 사용하는 동일한 기사 원문     |
| ❓ Questions | 지정된 질문 파일              |
| 🤖 Model    | 모델 ID 및 sampling 설정    |
| 💬 Prompts  | S1, S2, S3에서 사용하는 프롬프트 |
| 🔢 Order    | `S1 → S2 → S3` 순서      |

각 실행은 새로운 `run` 폴더에 저장되며, **이전 실행 결과를 덮어쓰지 않습니다.**

또한 API Key 자체는 어떤 파일에도 저장하지 않습니다.

---

# 🛠️ Before a Live Run

실험을 실제로 실행하기 전에 다음 세 가지를 준비합니다.

### 1. Config 파일 생성

Example config를 복사합니다.

```bash
cp config/halo_single.example.json config/halo_single.json
```

실험에서 사용할 모델과 sampling 설정은 **제공된 값을 그대로 유지합니다.**

---

### 2. 원본 기사 입력

다음 파일에 **실험에 사용할 뉴스 기사의 전체 원문**을 입력합니다.

```text
datasets/halo_article.txt
```

보고서에는 기사 일부만 포함되어 있기 때문에, 보고서의 excerpt를 이용해 기사를 임의로 복원하지 않습니다.

> **반드시 원본 기사를 그대로 사용해야 합니다.**

동일한 기사 원문은 **S1, S2, S3의 모든 단계에 제공**됩니다.
따라서 각 단계의 모델은 항상 동일한 원문을 참고할 수 있습니다.

---

### 3. API Key 설정

API Key는 config 파일에 직접 입력하지 않습니다.

`model.api_key_env`에 지정된 **환경변수 이름**을 확인한 후 해당 환경변수에 API Key를 설정합니다.

```text
model.api_key_env
        ↓
환경변수에 저장된 API Key 사용
```

> ⚠️ API Key를 코드나 config 파일에 직접 작성하거나 GitHub에 업로드하지 마세요.

---

# ▶️ Run

Single-Agent 실험은 다음 명령어로 실행합니다.

```bash
python run_experiment.py --config config/halo_single.json
```

실행할 때마다 새로운 run 폴더가 생성됩니다.

```text
results/
└── <run-id>/
    ├── responses.jsonl
    ├── labels.template.csv
    ├── manifest.json
    └── config.snapshot.json
```

### 결과 파일

| 파일                     | 설명                                  |
| ---------------------- | ----------------------------------- |
| `responses.jsonl`      | 각 질문의 S1, S2, S3 원본 답변              |
| `labels.template.csv`  | 사람이 Hallucination을 평가하기 위한 Label 파일 |
| `manifest.json`        | 해당 실행의 데이터 및 실행 정보                  |
| `config.snapshot.json` | 실행 당시 사용한 모델 및 설정                   |

또한 실제 사용된 **Prompt와 Response의 hash**, **모델 설정 및 Article의 snapshot/hash**도 저장하여 실행 결과를 재현하고 검증할 수 있도록 합니다.

---

## 🧪 Dry Run

실제 API를 호출하기 전에 전체 파이프라인이 정상적으로 작동하는지 확인하려면 `--dry-run`을 사용할 수 있습니다.

```bash
python run_experiment.py \
  --config config/halo_single.json \
  --dry-run \
  --run-id smoke-test
```

`dry-run`은 실제 실험을 진행하기 전에 **설정과 실행 흐름을 확인하는 테스트용 실행**입니다.

---

# 🏷️ Label & Aggregate

실험이 끝난 후에는 각 답변을 **사람이 직접 평가**합니다.

코드는 Hallucination 여부를 자동으로 판단하지 않습니다.
따라서 처음 생성되는 Label 파일에는 평가가 필요한 항목이 `PENDING_MANUAL_LABEL`로 남습니다.

## Label 기준

### Hallucination

| 값   | 의미               |
| --- | ---------------- |
| `0` | Hallucination 없음 |
| `1` | Hallucination 있음 |

### Severity

Hallucination의 심각도를 **0~5점**으로 평가합니다.

### Propagation

Hallucination이 단계별로 어떻게 변화했는지를 기록합니다.

| 값            | 의미                           |
| ------------ | ---------------------------- |
| `Initial`    | 해당 단계에서 Hallucination이 처음 발생 |
| `Maintained` | 이전 단계의 Hallucination이 계속 유지됨 |
| `Removed`    | 이전 단계의 Hallucination이 제거됨    |
| `None`       | Hallucination이 없음            |

---

## 📝 Label 작성

실험이 끝나면 다음 파일이 생성됩니다.

```text
results/<run-id>/labels.template.csv
```

이 파일에는

```text
question_id × repetition × stage
```

기준으로 각 답변에 대한 Label 행이 생성됩니다.

각 답변을 확인한 후 **5개의 Label 항목을 직접 작성**합니다.

> Hallucination 판단은 자동화하지 않고 사람이 직접 수행하는 것이 본 실험의 기준입니다.

---

## 📊 결과 집계

Label 작성이 끝나면 다음 명령어를 실행합니다.

```bash
python aggregate_results.py \
  --run-dir results/<run-id> \
  --labels results/<run-id>/labels.template.csv
```

다음 결과 파일이 생성됩니다.

```text
labeled_responses.jsonl
stage_summary.csv
question_stage_summary.csv
```

반복 실행 결과는 삭제하거나 합쳐지지 않고 그대로 유지됩니다.
따라서 반복 실행을 기준으로 **Hallucination rate, Severity mean 등의 결과를 계산**할 수 있습니다.

---

# 🤖 Single-Agent ChatGPT Condition

Single-Agent 조건에서는 **GPT-4.1 하나의 모델을 3단계 모두 사용**합니다.

```text
GPT-4.1 → GPT-4.1 → GPT-4.1
```

각 단계에서는 원래 제공된 다음 프롬프트를 그대로 사용합니다.

```text
SINGLE_STAGE_1
SINGLE_STAGE_2
SINGLE_STAGE_3
```

실험에서는 **전체 Article Pack 데이터셋**을 사용하며, 각 단계에 동일한 원문 기사를 제공합니다.

Single-Agent 실험은 GitHub Actions의

> **Run HALO single-agent ChatGPT**

workflow를 통해 실행할 수 있습니다.

기본 설정은 **1개 질문만 실행하는 smoke test**이며, 각 실행 결과는 하나의 artifact로 저장됩니다.

---

# 🔄 Multi-Model Condition

Multi-Model 조건에서는 서로 다른 모델이 각 단계의 역할을 나누어 수행합니다.

```text
M1: GPT-4.1
      ↓
M2: Gemini 3.6 Flash
      ↓
M3: GPT-4.1
```

각 모델의 역할은 다음과 같습니다.

| Stage | Model            | Role                          |
| ----- | ---------------- | ----------------------------- |
| M1    | GPT-4.1          | Drafting                      |
| M2    | Gemini 3.6 Flash | Article-grounded Verification |
| M3    | GPT-4.1          | Final Editing                 |

즉,

**초안 작성 → 기사 기반 사실 검증 → 최종 답변 수정**

의 순서로 진행됩니다.

Multi-Model 실험은 다음 명령어로 실행합니다.

```bash
python run_multi_experiment.py --config config/halo_multi.json
```

각 Provider의 API Key는 환경변수로 관리하며, config 파일에 직접 저장하지 않습니다.

---

## ⏱️ Gemini Free Tier 제한

무료 Gemini Flash는 **분당 요청 수와 일일 요청 수에 제한**이 있습니다.

따라서 전체 **33개 질문을 한 번에 실행하지 않고 2번에 나누어 실행**합니다.

### Batch 1

```text
question_offset = 0
max_total_questions = 20
```

→ 처음 20개 질문 실행

### Batch 2

다음 daily quota window에서:

```text
question_offset = 20
max_total_questions = 20
```

→ 나머지 질문 실행

Gemini 호출 사이에는 무료 tier의 요청 제한을 고려하여 **13초 간격**을 둡니다.

---

# 📰 Article Packs

Article Pack은 하나의 기사를 실험에 사용할 수 있도록 묶어놓은 데이터입니다.

각 Article Pack에는 다음 세 가지가 포함됩니다.

```text
Article Snapshot
       +
Ground Truth
       +
Questions
```

실험할 Article Pack 목록은 다음 파일에서 관리합니다.

```text
datasets/article_packs/manifest.jsonl
```

따라서 하나의 명령어로 여러 Article Pack을 실행할 수 있으며, 모든 결과에는 어떤 기사에서 생성된 답변인지 확인할 수 있도록 `article_id`가 저장됩니다.

---

## ⚠️ Article Pack 주의사항

**검증되지 않은 자동 생성 Article Pack을 실험에 바로 추가하지 않습니다.**

Article Pack은 먼저 제공된 원본 기사로부터 정해진 dataset protocol에 따라 생성하고 검증해야 합니다.

검증이 완료된 Article Pack만 다음 manifest에 추가합니다.

```text
datasets/article_packs/manifest.jsonl
```

이 과정을 통해 실험에서 사용하는 **기사 원문, Ground Truth, 질문이 실제 평가에 적합한지 확인한 후 모델을 실행**합니다.
