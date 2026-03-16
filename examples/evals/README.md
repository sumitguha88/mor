# MOR Evaluation Datasets

This folder contains sample datasets for running LLM and ontology-assisted evaluations with MOR.

## Paint sample

- Dataset: `examples/evals/paint-v2-eval.json`
- Default area/version: `paint / V1`

Each dataset item contains:

- `input`: query, intent, area, and version
- `expected_output.expected_concepts`: concepts that should be surfaced
- `expected_output.expected_sections`: answer sections that should appear
- `expected_output.expected_terms`: key terminology that should be preserved
- `expected_output.reference_answer`: a short human-written reference

## Local dry run

Run the evaluation locally without Langfuse using the mock provider:

```bash
mor eval-llm \
  --dataset-path examples/evals/paint-v2-eval.json \
  --ontology-root ontology \
  --area paint \
  --version V1 \
  --mode ontology_assisted \
  --provider mock \
  --dry-run
```

## Langfuse upload

Upload the sample dataset to Langfuse:

```bash
mor langfuse-upload-dataset \
  --dataset-path examples/evals/paint-v2-eval.json \
  --dataset-name mor-paint-v2-eval
```

## Langfuse experiment

Run an experiment using a live LLM provider:

```bash
mor eval-llm \
  --dataset-path examples/evals/paint-v2-eval.json \
  --ontology-root ontology \
  --area paint \
  --version V1 \
  --mode ontology_assisted \
  --provider openai \
  --model gpt-4.1-mini
```

If you want Langfuse-hosted runs instead of local experiment items, first upload the dataset and then pass `--dataset-name mor-paint-v2-eval`.
