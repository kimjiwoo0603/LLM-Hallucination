# HALO 2.0 dataset workflow

Do not put a generated or scraped article directly into the benchmark. The workflow is:

1. Store candidates in `articles.candidates.jsonl` and `questions.candidates.jsonl`.
2. A human reviewer sets `review_status: approved` for articles and `annotation_status: approved` for questions.
3. Run `python run_halo_v2.py validate ...`.
4. Run `python run_halo_v2.py select ...` with a fixed seed and version.

The selection command writes a new immutable benchmark directory. It never changes the candidate files.

Candidate article fields: `article_id`, `title`, `article_text`, `source_name`, `original_url`, `published_at`, `category`, `review_status` plus optional canonical URL and provenance fields.

Candidate question fields: `question_id`, `article_id`, `question_type`, `difficulty` (`EASY`, `MEDIUM`, `HARD`, `ADVERSARIAL`), `question`, `false_premise`, `target_claim`, `evidence_basis`, `annotation_status`.

## 기존 v1 기사로 시작하기

`python build_v2_candidate_pool.py`는 기존에 보관된 사용자 제공 v1 기사 10개와 질문을 다음의 **검토 대기 후보**로만 변환합니다.

- `candidates/articles.candidates.jsonl`
- `candidates/questions.candidates.jsonl`
- `candidates/review_templates/`의 기사·질문 검토표
- `candidates/conversion_manifest.json`의 원본 파일 해시

이 명령은 기사 출처·발행일·범주·정답을 추정하거나, 후보를 승인하지 않습니다. 각 행은 `pending` 상태로 생성되며, 검토자가 원문 출처와 근거를 확인한 뒤에만 `approved`로 바꿀 수 있습니다.
