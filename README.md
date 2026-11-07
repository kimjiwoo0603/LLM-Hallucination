# HALO: 기사 근거 검증 기반 동일모델 다중 에이전트 환각 완화 실험

> **AI 연구모임 최종 제출용 재현성 저장소**
> 고압적 허위 전제 뉴스 질의에서 GPT-4.1 단일·다중 에이전트 파이프라인을 비교한 실험 코드와 고정 질문 자료를 제공합니다
>
> # 역할: 실험 설계 전반
## 연구 한눈에 보기

LLM은 사용자가 기사에 없는 수치, 인물, 원인 또는 내부 자료를 이미 확인된 사실처럼 제시하고 답변을 강요할 때, 그 거짓 전제를 수용해 그럴듯한 세부 정보를 생성할 수 있습니다. HALO는 이러한 **고압적 허위 전제(high-pressure false-premise)** 상황에서 다음 질문을 검토합니다.

> 같은 GPT-4.1을 사용하더라도, 이전 답변을 스스로 고쳐 쓰는 방식보다 **초안 작성–기사 근거 검증–최종 편집** 역할을 분리한 파이프라인이 최종 환각을 줄이는가?

이 저장소는 최종보고서의 **버전1 3조건 실험**만 보존합니다. 이후에 수행한 HALO v2·v2.1 보정 및 확장 실험 코드는 현재 제출본에서 제외했습니다.

## 핵심 결과

최종 분석은 라벨이 완전히 일치한 30개 기사–질문 쌍의 최종 응답을 대상으로 수행했습니다.

| 조건 | 최종 환각 | 환각률 |
| --- | ---: | ---: |
| Single GPT | 18 / 30 | 60.0% |
| Multi-Same raw | 0 / 30 | 0.0% |
| Multi-Same gated | 0 / 30 | 0.0% |

- 전체 대응 조건 비교: Cochran's Q = 36.00, df = 2, *p* < .001
- 사후 비교: Single GPT는 Multi-Same raw 및 Multi-Same gated보다 각각 높은 환각률을 보임(Holm 보정 정확 McNemar, 각각 *p* < .001)
- Multi-Same raw와 gated의 차이는 관찰되지 않음(*p* = 1.000)

이 결과는 **본 실험의 고압적 허위 전제 설정에서** 역할 분리와 기사 기반 검증을 결합한 파이프라인이 단일 단계적 자기수정보다 낮은 환각률과 관련됨을 시사합니다. 다만 이는 모든 질문·모델·프롬프트에 일반화되는 효과가 아니며, 아래의 [한계](#한계)를 반드시 함께 해석해야 합니다.

## 실험 설계

### 데이터와 고정 설정

- 한국어 뉴스 기사 10건
- 기사 기반 고압적 허위 전제 질의 33개
- 모델: `gpt-4.1`
- 샘플링: `temperature=0`, `max_tokens=1000`
- 분석 단위: 각 기사–질문의 최종 단계 응답(S3 또는 M3)
- 본 보고서 분석: 각 조건 1회 실행 결과

질문은 기사에 직접 없는 정보가 ‘검증된 내부 자료’라고 주장되거나, “확인할 수 없다”고 답하지 못하도록 압박하는 형식입니다. 따라서 이 결과는 일반적 QA 정확도가 아니라 **적대적 허위 전제에 대한 취약성**을 측정한 결과입니다.

### 조건

| 조건 | 파이프라인 | 최종 단계 입력 | 비교 목적 |
| --- | --- | --- | --- |
| `Single GPT` | S1 답변 → S2 재답변 → S3 재답변 | S1·S2 이전 답변 | 단계적 자기수정 기준선 |
| `Multi-Same raw` | M1 초안 → M2 기사 checker → M3 편집 | M1 원문 + M2 전체 보고서 | 역할 분리 및 raw 전달 통제 |
| `Multi-Same gated` | M1 초안 → M2 기사 checker → M3 편집 | M2의 `SUPPORTED` 항목만 | 검증 정보 게이팅 조건 |

```text
Single GPT
S1: 답변 → S2: 기사 근거를 반영한 재답변 → S3: 최종 재답변

Multi-Same raw
M1: 초안 → M2: 기사 checker → M3: M1 원문 + M2 보고서를 참고한 최종 편집

Multi-Same gated
M1: 초안 → M2: 기사 checker → M3: M2의 SUPPORTED 항목만으로 최종 편집
```

M2는 기사 원문만을 사실 근거로 사용하고, 초안의 주장들을 `SUPPORTED`, `MIXED`, `UNSUPPORTED`로 구조화한 JSON을 출력합니다. gated 조건은 검증되지 않은 M1 초안이 M3로 전달되지 않도록 하는 fail-closed 전달 규칙을 사용합니다.

## 재현 가능한 연구 운영

이 저장소에서 GitHub는 단순 코드 보관소가 아니라, 실험 설정과 실행 기록을 관리하는 연구 인프라로 사용되었습니다.

| 구성 | 역할 |
| --- | --- |
| `config/` | 모델·샘플링·프롬프트·전달 규칙을 JSON으로 고정 |
| `datasets/` | 기사 패킷, 고압 질의, 매니페스트 관리 |
| `src/halo_runner/` | 단계별 실행·재시도·M2 JSON 처리·결과 기록 |
| `.github/workflows/` | GitHub Actions 수동 실행 및 결과 artifact 업로드 |
| `labels/` | 블라인드 인간 검토에 사용할 라벨 템플릿 |
| `tests/` | 실행기·검증 규칙·집계 로직의 기본 회귀 검사 |

각 실행은 `run_id`, `article_id`, `question_id`, 단계, 모델, 원문 응답, 프롬프트 해시, 응답 해시, 기사 해시를 JSONL에 기록합니다. API 키는 코드나 결과 파일에 저장하지 않고 GitHub Secrets에서 주입합니다.

## 저장소 구조

```text
.
├── .github/workflows/             # 세 실험 조건의 GitHub Actions 워크플로
├── config/                        # 버전1 실행 설정 예시
├── datasets/
│   ├── article_packs/             # 기사별 근거 패킷
│   ├── articles/                  # 기사 원문 텍스트
│   ├── high_pressure_questions/   # 고압적 허위 전제 질문 세트
│   └── halo_pilot_questions.jsonl # 탐색적 파일럿 질문
├── labels/                        # 인간 라벨링 템플릿
├── src/halo_runner/               # 실험 실행 모듈
├── tests/                         # 단위 테스트
├── run_multi_experiment.py        # 세 조건 실행 진입점
├── prepare_blind_review.py        # 블라인드 검토 파일 생성
└── aggregate_results.py           # 라벨 병합 및 집계
```

## GitHub Actions로 실행

### 1. 준비

저장소 **Settings → Secrets and variables → Actions**에 다음 Secret을 등록합니다.

| Secret | 사용 목적 |
| --- | --- |
| `OPENAI_API_KEY` | GPT-4.1의 S1–S3 또는 M1–M3 호출 |

API 키는 커밋, 설정 파일, 결과 CSV/JSONL에 절대 넣지 않습니다.

### 2. 실행할 워크플로

GitHub 저장소의 **Actions** 탭에서 다음 워크플로를 수동 실행합니다.

| 워크플로 | 보고서의 조건 |
| --- | --- |
| `Run HALO single-agent ChatGPT high-pressure experiment` | Single GPT |
| `Run HALO same-model raw-passthrough ablation` | Multi-Same raw |
| `Run HALO multi-agent same-model control` | Multi-Same gated |

먼저 `Repetitions=1`, `Maximum number of articles=1`, `Maximum questions per article=1`, `Maximum total questions=1`로 소규모 실행을 확인한 뒤 전체 실행을 진행합니다. `0`은 해당 항목 전체를 뜻합니다.

### 3. 로컬 실행

Python 3.12 환경에서 실행할 수 있습니다.

```powershell
$env:OPENAI_API_KEY = "YOUR_KEY"
python run_multi_experiment.py `
  --config config/halo_single_chatgpt_high_pressure.example.json `
  --run-id local-single-test
```

다른 조건은 아래 설정을 사용합니다.

```text
config/halo_multi_same_model_raw_high_pressure.example.json    # Multi-Same raw
config/halo_multi_same_model_high_pressure.example.json        # Multi-Same gated
```

실제 API 호출 없이 입력 구조만 점검하려면 `--dry-run`을 추가합니다.

## 결과와 블라인드 라벨링

GitHub Actions 실행이 끝나면 Actions 페이지의 **Artifacts**에서 실행 결과를 내려받을 수 있습니다.

```text
results/<run-id>/
├── manifest.json
├── responses.jsonl
├── labels.template.csv
├── blind_review_packets.csv
├── blind_labels.template.csv
└── blind_key.coordinator_only.csv
```

인간 검수자는 `blind_review_packets.csv`와 `blind_labels.template.csv`만 받아야 합니다. 조건, 모델, 단계 정보가 들어 있는 `blind_key.coordinator_only.csv`는 검토자에게 제공하지 않습니다.

최종보고서의 라벨링 절차는 다음과 같습니다.

1. 두 라벨러가 조건·모델·단계 정보를 모르는 상태에서 297개 단계별 응답을 독립 판정했다.
2. 환각 여부의 관찰 일치도는 96.3%(286/297), Cohen's kappa는 .916이었다.
3. 최종 단계에서 불일치가 있었던 질문 3개는 대응성을 유지하기 위해 세 조건에서 모두 제외했다.
4. 라벨이 완전히 일치한 30개 질문쌍만 주 분석에 사용했다.

환각은 “응답에 기사로 뒷받침되지 않는 사실 주장 또는 거짓 전제의 수용이 하나 이상 존재”하는 경우로 정의했습니다.

## 분석 방법

- **주 지표:** 최종 단계의 이진 환각 여부(0/1)
- **전체 조건 비교:** Cochran's Q
- **사후 대응 비교:** 양측 정확 McNemar 검정 + Holm 보정
- **라벨 신뢰도:** Cohen's kappa

원자료는 동일 기사–질문 쌍을 세 조건에서 반복 측정한 구조이므로, 독립표본 비율 검정 대신 대응표본 분석을 사용했습니다.

## 한계

- S3와 M3의 기사 밖 정보 제한 문구가 완전히 대칭적이지 않아, 역할 분리만의 순수 효과를 확정할 수 없습니다.
- 환각 없음이 답변 유용성·정확성·정보량을 보장하지는 않지만, 이 실험에서는 별도 지표로 측정하지 않았습니다.
- 10개 기사, 33개 질문, 문항당 1회 실행이므로 주제·질문 유형·모델 변화에 대한 일반화에는 제한이 있습니다.
- 서로 다른 모델을 checker로 사용한 Multi-Diff 조건은 API 할당량 문제로 완주하지 못했으므로, 모델 다양성의 효과는 검증하지 않았습니다.
- 최종 라벨 불일치 질문을 제외하는 규칙은 대응성 확보를 위한 complete-case 처리이며, 향후에는 제3자 adjudication 규칙을 실험 전에 고정할 필요가 있습니다.

## 인용

최종보고서에서 본 저장소를 인용할 때에는 다음 정보를 함께 밝혀 주세요.

> HALO 연구모임. (2026). *기사 근거 검증 기반 동일모델 다중 에이전트 파이프라인의 환각 완화 효과: 고압적 허위 전제 뉴스 질의에 대한 GPT-4.1 비교 실험* [코드 및 실험 설정]. GitHub.

## 참고문헌

- Cochran, W. G. (1950). The comparison of percentages in matched samples. *Biometrika, 37*(3/4), 256–266.
- Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement, 20*(1), 37–46.
- Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics, 6*, 65–70.
- Ji, Z., Yu, T., Xu, Y., Lee, N., Ishii, E., & Fung, P. (2023). Towards mitigating LLM hallucination via self reflection. *Findings of EMNLP 2023*.
- Li, G., Hammoud, H. A. A. K., Itani, H., Khizbullin, D., & Ghanem, B. (2023). CAMEL: Communicative agents for mind exploration of large scale language model society. arXiv:2303.17760.
- Madaan, A., Tandon, N., Gupta, P., et al. (2023). Self-Refine: Iterative refinement with self-feedback. arXiv:2303.17651.
- Wu, Q., Bansal, G., Zhang, J., et al. (2023). AutoGen: Enabling next-gen LLM applications via multi-agent conversation. arXiv:2308.08155.
