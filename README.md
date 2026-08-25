HALO: 단계별 Hallucination 실험

이 저장소는 Single-Agent의 3단계 실험을 자동으로 실행하기 위한 코드입니다.

실험은 다음 순서로 진행됩니다.

SINGLE_STAGE_1 → SINGLE_STAGE_2 → SINGLE_STAGE_3

각 질문과 반복 실행마다 3개 단계의 원본 답변을 저장합니다. 또한 실제로 사용한 프롬프트와 답변의 hash 값, 모델 설정 및 기사 원문의 snapshot/hash도 함께 저장하여 실험을 재현할 수 있도록 합니다.

Pilot 실험에서는 다음 6개 질문을 사용합니다.

Q005, Q009, Q011, Q012, Q013, Q014

실행할 때 고정되는 것

하나의 실험(run)을 실행할 때 다음 항목은 동일하게 유지합니다.

기사 원문과 질문 파일
모델 이름과 모든 sampling 설정
3개의 Stage 프롬프트
S1 → S2 → S3의 실행 순서

각 실험은 새로운 run 폴더에 저장됩니다.
기존 실험 결과를 덮어쓰지 않습니다.

또한 API Key 자체는 파일이나 결과에 저장하지 않습니다.

Live Run 전에 준비할 것
1. Config 파일 만들기

다음 파일을 복사합니다.

config/halo_single.example.json

복사한 파일의 이름을 다음과 같이 변경합니다.

config/halo_single.json
2. 기사 원문 넣기

다음 파일에 실험에 사용할 뉴스 기사의 전체 원문을 넣습니다.

datasets/halo_article.txt

보고서에는 기사의 일부 내용만 포함되어 있기 때문에, 보고서의 내용을 이용해 기사를 임의로 다시 만들면 안 됩니다.

반드시 원본 기사를 그대로 사용해야 합니다.

실험에서는 같은 기사 원문을 S1, S2, S3의 모든 단계에 전달합니다.

이는 각 단계에서 동일한 원문을 참고할 수 있도록 하기 위한 것입니다.

3. 모델 설정 확인

Single-Agent 실험에서는 GPT-4.1을 사용합니다.

모델과 sampling 설정은 실험에서 정해진 값을 사용하며, 하나의 실험 안에서는 임의로 변경하지 않습니다.

4. API Key 설정

API Key는 config 파일에 직접 입력하지 않습니다.

config의 model.api_key_env에 적혀 있는 환경변수 이름을 확인한 후, 해당 환경변수에 API Key를 설정합니다.

API Key가 코드나 GitHub에 저장되지 않도록 주의하세요.

실행

다음 명령어로 Single-Agent 실험을 실행합니다.

python run_experiment.py --config config/halo_single.json

실행하면 다음과 같은 결과 파일이 생성됩니다.

results/<run-id>/
├── responses.jsonl
├── labels.template.csv
├── manifest.json
└── config.snapshot.json
각 파일의 역할
responses.jsonl
→ 각 질문의 S1, S2, S3 원본 답변 저장
labels.template.csv
→ 나중에 사람이 Hallucination 등을 직접 평가할 때 사용하는 파일
manifest.json
→ 해당 실험에서 사용한 데이터와 실행 정보를 기록
config.snapshot.json
→ 해당 실험에서 사용한 모델 및 설정을 저장
코드가 제대로 작동하는지 먼저 확인하기

실제 API를 사용하기 전에 --dry-run으로 간단하게 테스트할 수 있습니다.

python run_experiment.py --config config/halo_single.json --dry-run --run-id smoke-test

--dry-run은 실제 실험을 진행하기 전에 전체 실행 과정이 정상적으로 작동하는지 확인하기 위한 테스트 모드입니다.

Label 및 결과 집계

실험이 끝나면 각 답변에 대해 사람이 직접 평가해야 합니다.

보고서에서는 다음 항목을 사용합니다.

Hallucination
0: 환각 없음
1: 환각 있음
Severity

Hallucination의 심각도를 0~5점으로 평가합니다.

Propagation

Hallucination이 단계별로 어떻게 변했는지를 기록합니다.

Initial: 해당 단계에서 처음 발생
Maintained: 이전 단계의 환각이 그대로 유지됨
Removed: 이전 단계의 환각이 제거됨
None: 환각 없음

코드는 이 판단을 자동으로 하지 않습니다.

따라서 처음에는 다음과 같이 표시됩니다.

PENDING_MANUAL_LABEL

즉, 실험자가 직접 답변을 확인하고 판단해야 합니다.

Label 작성

실험을 실행하면 자동으로 다음 파일이 생성됩니다.

results/<run-id>/labels.template.csv

이 파일에는

question_id × repetition × stage

별로 한 행씩 들어 있습니다.

각 답변을 확인한 후, 정해진 5개의 label 항목을 직접 작성합니다.

결과 집계

Label 작성을 완료한 후 다음 명령어를 실행합니다.

python aggregate_results.py --run-dir results/<run-id> --labels results/<run-id>/labels.template.csv

그러면 다음 파일이 생성됩니다.

labeled_responses.jsonl
stage_summary.csv
question_stage_summary.csv

반복 실행 결과도 그대로 유지되기 때문에, 여러 번 실행한 결과를 바탕으로 Hallucination 비율과 평균 Severity 등을 계산할 수 있습니다.

Single-Agent ChatGPT 조건

Single-Agent 조건에서는 같은 모델인 GPT-4.1을 3단계 모두 사용합니다.

GPT-4.1 → GPT-4.1 → GPT-4.1

각 단계에서는 원래 제공된 SINGLE_STAGE_1, SINGLE_STAGE_2, SINGLE_STAGE_3 프롬프트를 그대로 사용합니다.

또한 전체 기사 원문이 포함된 article-pack 데이터셋을 사용합니다.

실험은 GitHub Actions의 Run HALO single-agent ChatGPT workflow를 통해 실행할 수 있습니다.

기본 설정은 질문 1개만 실행하는 smoke test이며, 실행이 끝나면 해당 run의 결과를 하나의 artifact로 저장합니다.

Multi-Model 조건

Multi-Model 조건에서는 서로 다른 모델이 3단계의 역할을 나누어 수행합니다.

M1: GPT-4.1
        ↓
M2: Gemini 3.6 Flash
        ↓
M3: GPT-4.1

각 모델의 역할은 다음과 같습니다.

M1: 초안 작성(Drafting)
M2: 기사 기반 사실 검증(Article-grounded Verification)
M3: 최종 답변 수정(Final Editing)

Multi-Model 실험은 다음 코드로 실행합니다.

python run_multi_experiment.py --config config/halo_multi.json

각 모델의 API Key는 환경변수로 관리하며, config 파일에 직접 입력하지 않습니다.

Gemini 무료 사용량 제한

무료 Gemini Flash는 분당 요청 수와 일일 요청 수에 제한이 있습니다.

따라서 전체 33개 질문을 한 번에 실행하지 않고 두 번으로 나누어 실행합니다.

첫 번째 실행
question_offset = 0
max_total_questions = 20

→ 처음 20개 질문을 실행합니다.

다음 일일 quota가 초기화된 후
question_offset = 20
max_total_questions = 20

→ 나머지 질문을 실행합니다.

Article Pack

Article Pack은 하나의 기사를 실험에 사용할 수 있도록 묶어놓은 데이터입니다.

각 Article Pack에는 다음 내용이 포함됩니다.

기사 원문
+ Ground Truth
+ 해당 기사에 대한 질문

실험할 Article Pack 목록은 다음 파일에서 관리합니다.

datasets/article_packs/manifest.jsonl

따라서 하나의 명령어로 여러 기사를 순서대로 실행할 수 있으며, 각 결과에는 어떤 기사에서 나온 답변인지 알 수 있도록 article_id가 저장됩니다.

Article Pack 사용 시 주의사항

검증되지 않은 자동 생성 Article Pack을 실험에 바로 사용하면 안 됩니다.

Article Pack은 먼저 제공된 원본 기사에서 정해진 데이터셋 제작 절차에 따라 생성하고 검증해야 합니다.

검증이 완료된 Article Pack만 다음 파일에 등록합니다.

datasets/article_packs/manifest.jsonl

이 과정을 통해 실험에 사용되는 기사와 Ground Truth가 정확한지 확인한 후 모델을 평가할 수 있습니다.
