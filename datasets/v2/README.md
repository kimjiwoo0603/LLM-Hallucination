# HALO 2.0 dataset workflow

Do not put a generated or scraped article directly into the benchmark. The workflow is:

1. Store candidates in `articles.candidates.jsonl` and `questions.candidates.jsonl`.
2. A human reviewer sets `review_status: approved` for articles and `annotation_status: approved` for questions.
3. Run `python run_halo_v2.py validate ...`.
4. Run `python run_halo_v2.py select ...` with a fixed seed and version.

The selection command writes a new immutable benchmark directory. It never changes the candidate files.

Candidate article fields: `article_id`, `title`, `article_text`, `source_name`, `original_url`, `published_at`, `category`, `review_status` plus optional canonical URL and provenance fields.

Candidate question fields: `question_id`, `article_id`, `question_type`, `difficulty` (`EASY`, `MEDIUM`, `HARD`, `ADVERSARIAL`), `question`, `false_premise`, `target_claim`, `evidence_basis`, `annotation_status`.
