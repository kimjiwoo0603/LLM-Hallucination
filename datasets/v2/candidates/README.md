# HALO 2.0 후보 검토 대기열

이 폴더는 기존 HALO v1의 사용자 제공 기사 스냅샷을 기계적으로 옮긴 **후보 데이터**입니다. 이 파일만으로는 어떤 항목도 HALO 2.0 실험에 사용할 수 없습니다.

## 현재 상태

- 기사 후보: 10개
- 질문 후보: 66개 (기본 33개, 압박형 33개)
- 모든 기사: `review_status = pending`
- 모든 질문: `annotation_status = pending`
- 기본 본문 길이 1,500자 미만 경고: `V2C_A002`, `V2C_A003`, `V2C_A010`

## 검토자가 확인할 것

`review_templates/article_review.template.csv`에서는 기사마다 공개 원문 URL, 발행일, 범주, 검토 결정을 입력합니다. 공개 출처를 확인하지 못한 기사는 `approved`로 바꾸지 않습니다.

`review_templates/question_review.template.csv`에서는 질문마다 다음을 확인합니다.

1. 질문이 기사와 실제로 관련 있는가
2. 질문 속 거짓 또는 기사 밖 전제가 정확히 무엇인가
3. 판정에 쓸 기사 내 직접 근거 또는 ‘기사에 없음’ 근거는 무엇인가
4. 기본 질문과 압박형 질문의 유형·난이도가 적절한가

검토표를 완료한 뒤, 확인된 값만 `articles.candidates.jsonl`과 `questions.candidates.jsonl`에 반영한다. 그 다음에야 `run_halo_v2.py validate`와 고정 시드 선택 단계를 실행한다.

## 재현성

`conversion_manifest.json`은 변환에 사용된 각 원본 파일의 SHA-256 해시를 기록한다. 원본 기사나 질문이 바뀌면 이 후보군을 다시 생성하고 새 해시를 남긴다.
